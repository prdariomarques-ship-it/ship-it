"""Tools over tasks, calendar and notes — the personal-productivity API surface."""

from datetime import datetime

from agents.tools.base import Tool, ToolContext, ok
from models.calendar import CalendarEvent
from models.note import Note
from models.task import TaskPriority, TaskStatus
from repositories.base import SQLAlchemyRepository
from repositories.task import TaskRepository as _TaskRepo


class _EventRepo(SQLAlchemyRepository[CalendarEvent]):
    model = CalendarEvent


class _NoteRepo(SQLAlchemyRepository[Note]):
    model = Note


async def _create_task(
    context: ToolContext,
    title: str,
    description: str | None = None,
    priority: str = "medium",
    due_date: str | None = None,
) -> str:
    task = await _TaskRepo(context.db).create(
        user_id=context.user.id,
        title=title,
        description=description,
        priority=TaskPriority(priority),
        due_date=datetime.fromisoformat(due_date) if due_date else None,
        # Auto-linked to the contact this conversation is scoped to, if
        # any (None outside a WhatsApp conversation, e.g. the admin
        # dashboard) -- feeds the Contact Workspace's Tasks box for free,
        # no extra judgment required from the model.
        contact_id=context.contact_id,
    )
    return ok(task_id=task.id, title=task.title, status=task.status.value)


async def _list_tasks(context: ToolContext, status: str | None = None) -> str:
    filters: dict = {"user_id": context.user.id}
    if status:
        filters["status"] = TaskStatus(status)
    tasks = await _TaskRepo(context.db).list(limit=20, **filters)
    return ok(
        tasks=[
            {
                "id": task.id,
                "title": task.title,
                "status": task.status.value,
                "priority": task.priority.value,
                "due_date": task.due_date,
            }
            for task in tasks
        ]
    )


async def _complete_task(context: ToolContext, task_id: int) -> str:
    repository = _TaskRepo(context.db)
    task = await repository.get(int(task_id))
    if task is None or task.user_id != context.user.id:
        return ok(found=False)
    await repository.update(task, status=TaskStatus.DONE)
    return ok(task_id=task.id, status=task.status.value)


async def _create_event(
    context: ToolContext,
    title: str,
    starts_at: str,
    ends_at: str | None = None,
    location: str | None = None,
) -> str:
    event = await _EventRepo(context.db).create(
        user_id=context.user.id,
        title=title,
        starts_at=datetime.fromisoformat(starts_at),
        ends_at=datetime.fromisoformat(ends_at) if ends_at else None,
        location=location,
        contact_id=context.contact_id,
    )
    return ok(event_id=event.id, title=event.title, starts_at=event.starts_at)


async def _list_events(context: ToolContext) -> str:
    events = await _EventRepo(context.db).list(limit=20, user_id=context.user.id)
    return ok(
        events=[
            {
                "id": event.id,
                "title": event.title,
                "starts_at": event.starts_at,
                "location": event.location,
            }
            for event in events
        ]
    )


async def _create_note(context: ToolContext, title: str, content: str = "") -> str:
    note = await _NoteRepo(context.db).create(
        user_id=context.user.id,
        title=title,
        content=content,
        contact_id=context.contact_id,
    )
    return ok(note_id=note.id, title=note.title)


create_task_tool = Tool(
    name="create_task",
    description="Cria uma tarefa para o usuário.",
    handler=_create_task,
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Título da tarefa"},
            "description": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            "due_date": {"type": "string", "description": "Prazo em formato ISO 8601"},
        },
        "required": ["title"],
    },
)

list_tasks_tool = Tool(
    name="list_tasks",
    description="Lista as tarefas do usuário, opcionalmente filtrando por status.",
    handler=_list_tasks,
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "done", "cancelled"],
            }
        },
        "required": [],
    },
)

complete_task_tool = Tool(
    name="complete_task",
    description="Marca uma tarefa como concluída.",
    handler=_complete_task,
    parameters={
        "type": "object",
        "properties": {"task_id": {"type": "integer"}},
        "required": ["task_id"],
    },
)

create_event_tool = Tool(
    name="create_calendar_event",
    description="Cria um evento na agenda do usuário.",
    handler=_create_event,
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "starts_at": {
                "type": "string",
                "description": "Início em formato ISO 8601",
            },
            "ends_at": {"type": "string", "description": "Fim em formato ISO 8601"},
            "location": {"type": "string"},
        },
        "required": ["title", "starts_at"],
    },
)

list_events_tool = Tool(
    name="list_calendar_events",
    description="Lista os próximos eventos da agenda do usuário.",
    handler=_list_events,
)

create_note_tool = Tool(
    name="create_note",
    description="Cria uma nota para o usuário.",
    handler=_create_note,
    parameters={
        "type": "object",
        "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
        "required": ["title"],
    },
)
