"""Permanent semantic memory: provider embeddings stored in Qdrant, metadata in Postgres."""

import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.embedding import Embedding
from providers.llm.factory import get_embedding_provider
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class MemoryService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: AsyncQdrantClient | None = None
        self._collection_ready = False

    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(url=self._settings.qdrant_url)
        return self._client

    async def _ensure_collection(self) -> None:
        if self._collection_ready:
            return
        collections = await self.client.get_collections()
        names = {collection.name for collection in collections.collections}
        if self._settings.qdrant_collection not in names:
            await self.client.create_collection(
                collection_name=self._settings.qdrant_collection,
                vectors_config=VectorParams(
                    size=self._settings.embedding_dimensions, distance=Distance.COSINE
                ),
            )
        self._collection_ready = True

    async def store(
        self,
        db: AsyncSession,
        content: str,
        source: str,
        contact_id: int | None = None,
        external_id: str | None = None,
    ) -> Embedding:
        """Embed the content, upsert it into Qdrant and persist its metadata.

        `external_id` is an optional caller-owned key (e.g. a `Product.sku`)
        that lets a later call replace or drop this exact vector via
        `replace_by_external_id`/`delete_by_external_id` instead of the
        caller having to track `Embedding.id` itself.
        """
        await self._ensure_collection()
        vector = await get_embedding_provider().embed(content)
        vector_id = str(uuid.uuid4())

        await self.client.upsert(
            collection_name=self._settings.qdrant_collection,
            points=[
                PointStruct(
                    id=vector_id,
                    vector=vector,
                    payload={
                        "content": content,
                        "source": source,
                        "contact_id": contact_id,
                        "external_id": external_id,
                    },
                )
            ],
        )

        record = Embedding(
            contact_id=contact_id,
            source=source,
            content=content,
            vector_id=vector_id,
            external_id=external_id,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record

    async def delete(self, db: AsyncSession, embedding_ids: list[int]) -> None:
        """Remove specific memory/knowledge entries (Qdrant point + Postgres
        row) by `Embedding.id`. Generic — not tied to any one `source` —
        added for the Google Drive knowledge indexer (Sprint 3) to replace
        a file's stale chunks on re-indexing instead of accumulating
        duplicates forever; same minimal, additive-extension idiom already
        used for `auth/jwt.py::create_oauth_state_token`'s `purpose` param."""
        if not embedding_ids:
            return
        rows = (
            (await db.execute(select(Embedding).where(Embedding.id.in_(embedding_ids))))
            .scalars()
            .all()
        )
        vector_ids = [row.vector_id for row in rows]
        if vector_ids:
            await self._ensure_collection()
            await self.client.delete(
                collection_name=self._settings.qdrant_collection,
                points_selector=vector_ids,  # type: ignore[arg-type]  # list invariance false-positive
            )
        for row in rows:
            await db.delete(row)
        await db.commit()

    async def delete_by_external_id(
        self, db: AsyncSession, source: str, external_id: str
    ) -> None:
        """Remove every embedding tagged with this (source, external_id)
        pair. Looks the ids up in Postgres (which carries `external_id`)
        rather than a Qdrant payload filter, for the same reason `search()`
        over-fetches instead of filtering server-side: the installed
        qdrant-client has no combinator for this collection yet. Delegates
        to `delete()`, so it shares its Qdrant-then-Postgres ordering."""
        rows = (
            (
                await db.execute(
                    select(Embedding.id).where(
                        Embedding.source == source, Embedding.external_id == external_id
                    )
                )
            )
            .scalars()
            .all()
        )
        await self.delete(db, list(rows))

    async def replace_by_external_id(
        self,
        db: AsyncSession,
        content: str,
        source: str,
        external_id: str,
        contact_id: int | None = None,
    ) -> Embedding:
        """Re-embed an external record (e.g. a product) under a stable key:
        drops any previous vector(s) for this (source, external_id) first,
        so re-indexing never accumulates duplicate/stale chunks -- same
        intent as `delete()`'s docstring, specialized for the common case
        of a single caller-owned external key."""
        await self.delete_by_external_id(db, source, external_id)
        return await self.store(
            db, content, source, contact_id=contact_id, external_id=external_id
        )

    async def search(
        self, query: str, limit: int = 5, contact_id: int | None = None
    ) -> list[dict]:
        """Semantic search over the memory. Returns content + score, best first."""
        await self._ensure_collection()
        vector = await get_embedding_provider().embed(query)

        query_filter = None
        if contact_id is not None:
            query_filter = Filter(
                must=[
                    FieldCondition(key="contact_id", match=MatchValue(value=contact_id))
                ]
            )

        response = await self.client.query_points(
            collection_name=self._settings.qdrant_collection,
            query=vector,
            limit=limit,
            query_filter=query_filter,
        )
        return [
            {
                "content": point.payload.get("content", "") if point.payload else "",
                "source": point.payload.get("source", "") if point.payload else "",
                "contact_id": point.payload.get("contact_id")
                if point.payload
                else None,
                "score": point.score,
            }
            for point in response.points
        ]


memory_service = MemoryService()
