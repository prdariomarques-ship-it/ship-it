"""Permanent semantic memory: provider embeddings stored in Qdrant, metadata in SQL.

Qdrant and SQL cannot be committed atomically.  The external-key operations
therefore upsert a stable point first and commit metadata afterwards; a retry
converges because the point id is stable.  PostgreSQL serializes those
operations across workers with a transaction advisory lock.  SQLite uses a
process-local asyncio lock for isolated tests only (SQLite's own write lock
still protects the database, but this is not a PostgreSQL-lock test).
"""

import asyncio
import hashlib
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.embedding import Embedding
from providers.llm.factory import get_embedding_provider
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

_external_key_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


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

    @staticmethod
    def _external_key_lock_value(source: str, external_id: str) -> int:
        """Return a stable signed bigint accepted by pg_advisory_xact_lock."""
        digest = hashlib.sha256(
            f"{len(source)}:{source}\x00{len(external_id)}:{external_id}".encode()
        ).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=True)

    @asynccontextmanager
    async def _serialize_external_key(
        self, db: AsyncSession, source: str, external_id: str
    ) -> AsyncIterator[None]:
        """Lock before lookup, using a DB transaction lock on PostgreSQL."""
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            lock_value = self._external_key_lock_value(source, external_id)
            await db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_value)"),
                {"lock_value": lock_value},
            )
            yield
            return

        # SQLite has no advisory locks.  This is intentionally only a local
        # mutex: it makes isolated SQLite tests deterministic, not a
        # cross-worker/distributed serialization guarantee.
        lock_key = f"{source}\x00{external_id}"
        async with _external_key_locks[lock_key]:
            yield

    @staticmethod
    def _stable_external_vector_id(source: str, external_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"memory:{source}\x00{external_id}"))

    async def store(
        self,
        db: AsyncSession,
        content: str,
        source: str,
        contact_id: int | None = None,
        external_id: str | None = None,
    ) -> Embedding:
        """Embed the content, upsert it into Qdrant and persist its metadata."""
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
        """Delete vectors and metadata matching one source/key pair."""
        async with self._serialize_external_key(db, source, external_id):
            try:
                result = await db.execute(
                    select(Embedding).where(
                        Embedding.source == source,
                        Embedding.external_id == external_id,
                    )
                )
                rows = list(result.scalars().all())
                vector_ids = [row.vector_id for row in rows]
                if vector_ids:
                    await self._ensure_collection()
                    await self.client.delete(
                        collection_name=self._settings.qdrant_collection,
                        points_selector=vector_ids,  # type: ignore[arg-type]
                    )
                    for row in rows:
                        await db.delete(row)
                    await db.commit()
            except BaseException:
                await db.rollback()
                raise

    async def replace_by_external_id(
        self,
        db: AsyncSession,
        content: str,
        source: str,
        external_id: str,
        contact_id: int | None = None,
    ) -> Embedding:
        """Upsert one stable external key without deleting its old value first.

        Embedding and Qdrant failures happen before metadata is changed, so
        the old representation remains available.  A SQL commit failure can
        still leave Qdrant ahead of SQL; retrying this operation is safe and
        converges through the deterministic point id.
        """
        async with self._serialize_external_key(db, source, external_id):
            try:
                result = await db.execute(
                    select(Embedding)
                    .where(
                        Embedding.source == source,
                        Embedding.external_id == external_id,
                    )
                    .order_by(Embedding.id)
                )
                rows = list(result.scalars().all())
                if len(rows) > 1:
                    raise RuntimeError(
                        "Duplicate external-key metadata requires explicit reconciliation"
                    )
                record = rows[0] if rows else None
                vector_id = (
                    record.vector_id
                    if record is not None
                    else self._stable_external_vector_id(source, external_id)
                )

                await self._ensure_collection()
                vector = await get_embedding_provider().embed(content)
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

                if record is None:
                    record = Embedding(
                        contact_id=contact_id,
                        source=source,
                        content=content,
                        vector_id=vector_id,
                        external_id=external_id,
                    )
                    db.add(record)
                else:
                    record.contact_id = contact_id
                    record.content = content
                    # Keep the old id on updates, even for legacy rows.
                    record.vector_id = vector_id

                await db.commit()
                await db.refresh(record)
                return record
            except BaseException:
                await db.rollback()
                raise

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
