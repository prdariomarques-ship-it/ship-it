"""Response Validation: the last checkpoint before a reply reaches the user.

Deterministic, not another LLM call — validation must be cheap enough to run
on every response without materially adding latency or cost. It checks
exactly what the brief asks for: coherence (a non-empty, non-error reply),
tools executed (did any tool this turn actually fail), and consistency (the
reply isn't just a raw JSON error blob leaking through). When it fails, the
Cognitive Pipeline gets one bounded retry (never unbounded — see
`CognitivePipeline._MAX_VALIDATION_ATTEMPTS`) before giving up and returning
the best available answer rather than going silent.
"""
from pydantic import BaseModel

from agents.executor import ExecutedStep, is_tool_error


class ValidationResult(BaseModel):
    ok: bool
    issues: list[str] = []


class ResponseValidator:
    def validate(self, *, reply: str, steps: list[ExecutedStep]) -> ValidationResult:
        issues: list[str] = []

        if not reply or not reply.strip():
            issues.append("resposta vazia")
        elif reply.strip().startswith("{") and '"error"' in reply:
            issues.append("resposta é um erro bruto de ferramenta, não uma resposta ao usuário")

        for step in steps:
            if step.status == "error" or is_tool_error(step.result):
                issues.append(f"ferramenta '{step.tool}' falhou: {step.result[:200]}")

        return ValidationResult(ok=not issues, issues=issues)
