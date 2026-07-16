"""Response Validation: cheap, deterministic checks — no LLM call."""

from agents.executor import ExecutedStep
from orchestrator.validation import ResponseValidator


def test_valid_reply_with_no_tool_failures_passes():
    result = ResponseValidator().validate(reply="Tudo certo, tarefa criada.", steps=[])
    assert result.ok
    assert result.issues == []


def test_empty_reply_is_flagged():
    result = ResponseValidator().validate(reply="   ", steps=[])
    assert not result.ok
    assert "resposta vazia" in result.issues[0]


def test_raw_error_json_leaking_as_the_reply_is_flagged():
    result = ResponseValidator().validate(reply='{"error": "boom"}', steps=[])
    assert not result.ok


def test_failed_tool_step_is_flagged():
    step = ExecutedStep(
        tool="create_task", arguments={}, result='{"error": "DB down"}', status="error"
    )
    result = ResponseValidator().validate(reply="Feito!", steps=[step])
    assert not result.ok
    assert "create_task" in result.issues[0]


def test_successful_tool_steps_do_not_block_validation():
    step = ExecutedStep(
        tool="list_tasks", arguments={}, result='{"ok": true, "tasks": []}', status="ok"
    )
    result = ResponseValidator().validate(reply="Você não tem tarefas.", steps=[step])
    assert result.ok
