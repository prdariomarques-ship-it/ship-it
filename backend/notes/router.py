"""Note endpoints: CRUD plus search (title/content/tags, case-insensitive,
partial match), pinned/archived organization, and a `contact_id` reserved
for a future "link this note to a contact" feature (unused by any endpoint
today -- see docs/NOTES.md for the forward-compatibility rationale).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from database.session import get_db
from models.note import Note
from repositories.note import NoteRepository

router = APIRouter(prefix="/notes", tags=["notes"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    content: str
    tags: list[str]
    pinned: bool
    archived: bool
    contact_id: int | None
    created_at: datetime
    updated_at: datetime


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = ""
    tags: list[str] = []
    pinned: bool = False


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = None
    tags: list[str] | None = None
    pinned: bool | None = None
    archived: bool | None = None


async def _get_owned_note_or_404(
    repository: NoteRepository, note_id: int, user_id: int
) -> Note:
    note = await repository.get(note_id)
    if note is None or note.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found"
        )
    return note


@router.get("", response_model=list[NoteRead])
async def list_notes(
    db: DbSession,
    current_user: CurrentUser,
    q: Annotated[str | None, Query(description="Search title/content/tags")] = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Note]:
    return await NoteRepository(db).search(
        user_id=current_user.id,
        query=q,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )


@router.get("/count")
async def count_notes(db: DbSession, current_user: CurrentUser) -> dict[str, int]:
    return {"count": await NoteRepository(db).count(user_id=current_user.id)}


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate, db: DbSession, current_user: CurrentUser
) -> Note:
    return await NoteRepository(db).create(
        user_id=current_user.id,
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
        pinned=payload.pinned,
    )


@router.get("/{note_id}", response_model=NoteRead)
async def get_note(note_id: int, db: DbSession, current_user: CurrentUser) -> Note:
    return await _get_owned_note_or_404(NoteRepository(db), note_id, current_user.id)


@router.patch("/{note_id}", response_model=NoteRead)
async def update_note(
    note_id: int, payload: NoteUpdate, db: DbSession, current_user: CurrentUser
) -> Note:
    repository = NoteRepository(db)
    note = await _get_owned_note_or_404(repository, note_id, current_user.id)
    return await repository.update(note, **payload.model_dump(exclude_unset=True))


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: int, db: DbSession, current_user: CurrentUser) -> None:
    repository = NoteRepository(db)
    note = await _get_owned_note_or_404(repository, note_id, current_user.id)
    await repository.delete(note)
