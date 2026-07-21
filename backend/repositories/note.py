from models.note import Note
from repositories.base import SQLAlchemyRepository


class NoteRepository(SQLAlchemyRepository[Note]):
    model = Note

    async def search(
        self,
        user_id: int,
        query: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Note]:
        """Case-insensitive, partial match across title/content/tags.

        Filtered/sorted in Python rather than pushed into SQL: tags is a
        JSON list, which has no portable (SQLite + Postgres) "does any
        element contain this substring, case-insensitively" query, and a
        personal note-taking tool's total row count per user is small enough
        that this isn't a real cost. `GET /notes?q=...` is the natural seam
        to swap in `MemoryManager`'s existing semantic search later, without
        changing the endpoint's contract -- see docs/NOTES.md.
        """
        candidates = await self.list(
            user_id=user_id, limit=10_000, offset=0, order_desc=True
        )
        if not include_archived:
            candidates = [note for note in candidates if not note.archived]
        if query:
            needle = query.strip().lower()
            if needle:
                candidates = [note for note in candidates if _matches(note, needle)]
        candidates.sort(key=lambda note: (not note.pinned, -note.id))
        return candidates[offset : offset + limit]


def _matches(note: Note, needle: str) -> bool:
    if needle in note.title.lower():
        return True
    if needle in note.content.lower():
        return True
    return any(needle in str(tag).lower() for tag in note.tags)
