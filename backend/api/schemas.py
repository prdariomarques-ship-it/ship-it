"""Pydantic schemas for the CRUD resources."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models.message import MessageDirection, MessageMediaType
from models.task import TaskPriority, TaskStatus


class _Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# --- Contacts -------------------------------------------------------------
class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    categories: list[str] = []
    summary: str | None = None
    preferences: dict = {}
    tags: list[str] = []


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    categories: list[str] | None = None
    summary: str | None = None
    preferences: dict | None = None
    tags: list[str] | None = None


class ContactRead(_Read):
    name: str
    phone: str | None
    categories: list
    summary: str | None
    preferences: dict
    tags: list
    last_interaction_at: datetime | None


# --- Messages -------------------------------------------------------------
class MessageRead(_Read):
    contact_id: int
    direction: MessageDirection
    media_type: MessageMediaType
    content: str
    external_id: str | None


# --- Tasks ----------------------------------------------------------------
class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: datetime | None = None


class TaskRead(_Read):
    user_id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: datetime | None


# --- Calendar ---------------------------------------------------------------
class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    location: str | None = None
    starts_at: datetime
    ends_at: datetime | None = None
    reminder_minutes: int | None = Field(default=None, ge=0)


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    location: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    reminder_minutes: int | None = Field(default=None, ge=0)


class CalendarEventRead(_Read):
    user_id: int
    title: str
    description: str | None
    location: str | None
    starts_at: datetime
    ends_at: datetime | None
    reminder_minutes: int | None


# --- Notes ------------------------------------------------------------------
class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = ""
    tags: list[str] = []


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = None
    tags: list[str] | None = None


class NoteRead(_Read):
    user_id: int
    title: str
    content: str
    tags: list


# --- Church -----------------------------------------------------------------
class ChurchMemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    role: str | None = Field(default=None, max_length=100)
    ministries: list[str] = []
    prayer_requests: list[str] = []
    notes: str | None = None


class ChurchMemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    role: str | None = Field(default=None, max_length=100)
    ministries: list[str] | None = None
    prayer_requests: list[str] | None = None
    notes: str | None = None


class ChurchMemberRead(_Read):
    name: str
    phone: str | None
    role: str | None
    ministries: list
    prayer_requests: list
    notes: str | None


# --- Store ------------------------------------------------------------------
class StoreCustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    orders: list = []
    notes: str | None = None


class StoreCustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    orders: list | None = None
    notes: str | None = None


class StoreCustomerRead(_Read):
    name: str
    phone: str | None
    email: str | None
    orders: list
    notes: str | None


# --- Logs ---------------------------------------------------------------
class LogRead(_Read):
    level: str
    source: str
    message: str
    payload: dict
