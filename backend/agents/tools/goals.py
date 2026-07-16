"""Agent tools over GoalManager -- the Planner-facing surface of persistent
goals. Deliberately excludes approval: `approve_goal` only exists on the
admin-only HTTP endpoint (`POST /api/goals/{id}/approve`), never as a tool an
agent (i.e. the LLM) can call -- that is the human-approval boundary itself,
not an oversight.
"""
from datetime import datetime

from agents.tools.base import Tool, ToolContext, ok
from goals.service import ApprovalRequiredError, GoalService
from models.goal import GoalPriority, GoalStatus
from repositories.goal import GoalRepository


async def _create_goal(
    context: ToolContext,
    title: str,
    description: str | None = None,
    priority: str = "medium",
    deadline: str | None = None,
    recurrence_interval_days: int | None = None,
) -> str:
    goal = await GoalService(context.db).create_goal(
        user_id=context.user.id,
        title=title,
        description=description,
        priority=GoalPriority(priority),
        deadline=datetime.fromisoformat(deadline) if deadline else None,
        recurrence_interval_days=recurrence_interval_days,
    )
    return ok(goal_id=goal.id, title=goal.title, status=goal.status.value)


async def _list_goals(context: ToolContext, status: str | None = None) -> str:
    filters: dict = {"user_id": context.user.id}
    if status:
        filters["status"] = GoalStatus(status)
    goals = await GoalRepository(context.db).list(limit=20, **filters)
    return ok(
        goals=[
            {
                "id": goal.id,
                "title": goal.title,
                "status": goal.status.value,
                "priority": goal.priority.value,
                "deadline": goal.deadline,
                "progress_percent": goal.progress_percent,
            }
            for goal in goals
        ]
    )


async def _update_goal_progress(context: ToolContext, goal_id: int, progress_percent: int) -> str:
    repository = GoalRepository(context.db)
    goal = await repository.get(int(goal_id))
    if goal is None or goal.user_id != context.user.id:
        return ok(found=False)
    updated = await GoalService(context.db).update_progress(goal, progress_percent)
    return ok(goal_id=updated.id, progress_percent=updated.progress_percent, status=updated.status.value)


async def _complete_goal(context: ToolContext, goal_id: int) -> str:
    repository = GoalRepository(context.db)
    goal = await repository.get(int(goal_id))
    if goal is None or goal.user_id != context.user.id:
        return ok(found=False)
    try:
        updated = await GoalService(context.db).update_status(goal, GoalStatus.COMPLETED)
    except ApprovalRequiredError as exc:
        return ok(found=True, error=str(exc))
    return ok(goal_id=updated.id, status=updated.status.value)


create_goal_tool = Tool(
    name="create_goal",
    description=(
        "Cria uma meta persistente para o usuário (diferente de uma tarefa simples: "
        "pode ter prazo, se repetir, e depender de outras metas)."
    ),
    handler=_create_goal,
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Título da meta"},
            "description": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
            "deadline": {"type": "string", "description": "Prazo em formato ISO 8601"},
            "recurrence_interval_days": {
                "type": "integer",
                "description": "Se a meta se repete, o intervalo em dias entre ocorrências",
            },
        },
        "required": ["title"],
    },
)

list_goals_tool = Tool(
    name="list_goals",
    description="Lista as metas do usuário, opcionalmente filtrando por status.",
    handler=_list_goals,
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["awaiting_approval", "pending", "in_progress", "completed", "cancelled"],
            }
        },
        "required": [],
    },
)

update_goal_progress_tool = Tool(
    name="update_goal_progress",
    description="Atualiza o percentual de progresso (0-100) de uma meta.",
    handler=_update_goal_progress,
    parameters={
        "type": "object",
        "properties": {
            "goal_id": {"type": "integer"},
            "progress_percent": {"type": "integer", "minimum": 0, "maximum": 100},
        },
        "required": ["goal_id", "progress_percent"],
    },
)

complete_goal_tool = Tool(
    name="complete_goal",
    description="Marca uma meta como concluída.",
    handler=_complete_goal,
    parameters={
        "type": "object",
        "properties": {"goal_id": {"type": "integer"}},
        "required": ["goal_id"],
    },
)
