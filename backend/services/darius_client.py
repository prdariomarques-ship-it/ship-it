"""Authenticated HTTP adapter for DARIUS OSS (the canonical task runtime).

Contract: DARIUS `DARIUS_API_CONTRACTS.md` (v1). This module is a *client only*:
it never touches the DARIUS database and never re-implements queueing,
leasing, approval or scheduling -- those guarantees live in DARIUS.

Behavior that matters operationally:
  * Every response is validated; a malformed body is `DariusInvalidResponse`,
    never a guessed value.
  * Retries only where repeating is safe: GETs and task creation carrying an
    Idempotency-Key. Decisions (approve / reject / cancel) are sent ONCE; if the
    reply is lost the error carries `outcome_unknown=True` and the caller must
    read the task state instead of repeating the decision.
  * A circuit breaker fails fast after consecutive transport/5xx failures.
  * The token is never logged, never in `repr`, never in an error message.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

TaskStatus = Literal["PENDING", "QUEUED", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"]
MAX_PAGE_SIZE = 200


# ---- errors ---------------------------------------------------------------
class DariusError(Exception):
    """Base error. `outcome_unknown` is True when a state-changing request may have been applied."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        task_status: str | None = None,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.task_status = task_status
        self.outcome_unknown = outcome_unknown


class DariusNotConfigured(DariusError):
    """DARIUS_BASE_URL or the needed token is empty: the integration is off."""


class DariusUnavailable(DariusError):
    """Timeout, connection failure, 5xx, or open circuit."""


class DariusInvalidResponse(DariusError):
    """The runtime answered, but not with the documented contract."""


class DariusAuthError(DariusError):
    """401 / 403: credential rejected or not allowed to perform the operation."""


class DariusNotFound(DariusError):
    """404: the task does not exist or belongs to another client."""


class DariusConflict(DariusError):
    """409: invalid transition (not awaiting approval, already decided/finished)."""


class DariusRequestError(DariusError):
    """Other 4xx (bad request, payload too large, idempotency conflict, quota, rate limit)."""

    def __init__(self, message: str, *, retry_after: float | None = None, **kw: Any) -> None:
        super().__init__(message, **kw)
        self.retry_after = retry_after


# ---- response models (extra fields are tolerated: forward compatible) -------
class _M(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TaskSummary(_M):
    id: str
    objective: str
    status: TaskStatus
    agentId: str | None = None
    createdAt: str
    updatedAt: str


class RetryInfo(_M):
    attempts: int
    nextAttemptAt: int


class TaskResult(_M):
    id: str
    status: TaskStatus
    done: bool
    result: str | None = None
    error: str | None = None
    # What DARIUS knows about the external effect of a FAILED task (see DARIUS `FailureClass`) and, while a
    # QUEUED task backs off after a transient failure, the retry schedule. Absent on older runtimes.
    failureClass: str | None = None
    retry: RetryInfo | None = None
    updatedAt: str


class RuntimeMetrics(_M):
    """`GET /api/admin/metrics` of the runtime. Sections stay open dicts: the runtime states what it cannot
    know as null + reason, and the panel must show exactly that (never a made-up 0)."""

    generatedAt: int
    scope: dict[str, str] = {}
    tasks: dict[str, Any]
    queue: dict[str, Any]
    engine: dict[str, Any]
    scheduler: dict[str, Any]


class TraceStep(_M):
    state: str
    timestamp: str | None = None
    output: str | None = None
    error: str | None = None


class TaskState(_M):
    taskId: str
    objective: str
    status: TaskStatus
    currentState: str | None = None
    iterations: int = 0
    trace: list[TraceStep] = []


class DecisionAck(_M):
    id: str
    status: TaskStatus
    decision: Literal["APPROVED", "REJECTED"] | None = None


@dataclass(frozen=True)
class TaskPage:
    items: list[TaskSummary]
    total: int
    next_offset: int | None


# ---- circuit breaker --------------------------------------------------------
class CircuitBreaker:
    """Opens after `threshold` consecutive failures; half-opens after `cooldown`."""

    def __init__(self, threshold: int, cooldown: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.threshold = max(1, threshold)
        self.cooldown = max(0.0, cooldown)
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        return "half_open" if self._clock() - self._opened_at >= self.cooldown else "open"

    def allow(self) -> bool:
        return self.state != "open"

    def success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold or self._opened_at is not None:
            # a failed half-open probe re-opens for a full cooldown
            self._opened_at = self._clock()

    @property
    def consecutive_failures(self) -> int:
        return self._failures


# ---- client -----------------------------------------------------------------
Sleeper = Callable[[float], Awaitable[None]]


class DariusClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 10.0,
        max_attempts: int = 3,
        backoff: float = 0.5,
        breaker: CircuitBreaker | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleeper = asyncio.sleep,
        label: str = "darius",
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._token = token or ""
        self._timeout = timeout
        self._max_attempts = max(1, max_attempts)
        self._backoff = max(0.0, backoff)
        self._transport = transport
        self._sleep = sleep
        self.label = label
        self.breaker = breaker or CircuitBreaker(5, 30.0)

    def __repr__(self) -> str:  # never include the token
        return f"DariusClient(label={self.label!r}, base_url={self._base_url!r}, circuit={self.breaker.state})"

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._token)

    # -- transport ------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        retry: bool,
    ) -> httpx.Response:
        if not self.configured:
            raise DariusNotConfigured("DARIUS integration is not configured")
        if not self.breaker.allow():
            raise DariusUnavailable("DARIUS circuit open: failing fast", code="CIRCUIT_OPEN")

        attempts = self._max_attempts if retry else 1
        hdrs = {"Authorization": f"Bearer {self._token}", "Accept": "application/json", **(headers or {})}
        last: DariusError | None = None
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(
                    base_url=self._base_url, timeout=self._timeout, transport=self._transport
                ) as http:
                    response = await http.request(method, path, params=params, json=json_body, headers=hdrs)
            except httpx.HTTPError as exc:
                self.breaker.failure()
                last = DariusUnavailable(
                    f"DARIUS unreachable ({type(exc).__name__})",
                    outcome_unknown=method != "GET",
                )
            else:
                if response.status_code >= 500 or response.status_code == 429:
                    if response.status_code >= 500:
                        self.breaker.failure()
                    last = self._http_error(response, outcome_unknown=method != "GET" and response.status_code >= 500)
                else:
                    self.breaker.success()
                    if response.status_code >= 400:
                        raise self._http_error(response)
                    return response
            if attempt + 1 < attempts and (retry_after := getattr(last, "retry_after", None)) is not None:
                await self._sleep(min(float(retry_after), 5.0))
            elif attempt + 1 < attempts:
                await self._sleep(self._backoff * (2**attempt))
            if not self.breaker.allow():
                break
        assert last is not None
        raise last

    @staticmethod
    def _error_body(response: httpx.Response) -> tuple[str, str | None, str | None]:
        try:
            body = response.json()
        except ValueError:
            return f"HTTP {response.status_code}", None, None
        if not isinstance(body, dict):
            return f"HTTP {response.status_code}", None, None
        # Only documented, non-secret fields are surfaced; never the raw body.
        def text(key: str) -> str | None:
            value = body.get(key)
            return value if isinstance(value, str) else None

        return (text("error") or f"HTTP {response.status_code}")[:200], text("code"), text("status")

    def _http_error(self, response: httpx.Response, *, outcome_unknown: bool = False) -> DariusError:
        s = response.status_code
        msg, code, task_status = self._error_body(response)
        kw: dict[str, Any] = {"status_code": s, "code": code, "task_status": task_status}
        if s >= 500:
            return DariusUnavailable(f"DARIUS server error: {msg}", outcome_unknown=outcome_unknown, **kw)
        if s in (401, 403):
            return DariusAuthError(msg, **kw)
        if s == 404:
            return DariusNotFound(msg, **kw)
        if s == 409:
            return DariusConflict(msg, **kw)
        retry_after: float | None = None
        if s == 429:
            try:
                retry_after = float(response.headers.get("Retry-After", ""))
            except ValueError:
                retry_after = None
        return DariusRequestError(msg, retry_after=retry_after, **kw)

    @staticmethod
    def _parse(model: type[BaseModel], response: httpx.Response, *, outcome_unknown: bool = False) -> Any:
        try:
            return model.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise DariusInvalidResponse(
                f"DARIUS returned an invalid {model.__name__}",
                status_code=response.status_code,
                outcome_unknown=outcome_unknown,
            ) from exc

    # -- operations -------------------------------------------------------------
    async def health(self) -> dict[str, Any]:
        """Liveness; the runtime keeps this route open, but a rejected token still surfaces for others."""
        response = await self._request("GET", "/api/health", retry=False)
        try:
            body = response.json()
        except ValueError as exc:
            raise DariusInvalidResponse("DARIUS returned an invalid health body") from exc
        if not isinstance(body, dict):
            raise DariusInvalidResponse("DARIUS returned an invalid health body")
        return body

    async def create_task(
        self,
        objective: str,
        *,
        idempotency_key: str,
        model_name: str | None = None,
        completion: Literal["non_empty"] | None = None,
    ) -> TaskSummary:
        """Creates a task. The Idempotency-Key is mandatory here so a retry can never create a second one.

        ``completion="non_empty"`` asks DARIUS to accept any non-empty answer as success (free-text
        replies); omitted keeps the legacy contract (the result must contain "done").
        """
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        body: dict[str, Any] = {"objective": objective}
        if model_name:
            body["modelName"] = model_name
        if completion:
            body["completion"] = completion
        response = await self._request(
            "POST", "/api/tasks", json_body=body, headers={"Idempotency-Key": idempotency_key.strip()}, retry=True
        )
        return self._parse(TaskSummary, response, outcome_unknown=True)

    async def list_tasks(self, *, status: str | None = None, limit: int = 50, offset: int = 0) -> TaskPage:
        if not 1 <= limit <= MAX_PAGE_SIZE or offset < 0:
            raise ValueError("limit must be 1-200 and offset >= 0")
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        response = await self._request("GET", "/api/tasks", params=params, retry=True)
        try:
            raw = response.json()
            if not isinstance(raw, list):
                raise ValueError("not a list")
            items = [TaskSummary.model_validate(x) for x in raw]
            total = int(response.headers["X-Total-Count"])
            nxt_raw = response.headers.get("X-Next-Offset")
            nxt = int(nxt_raw) if nxt_raw is not None else None
        except (ValueError, KeyError, ValidationError) as exc:
            raise DariusInvalidResponse(
                "DARIUS returned an invalid task page", status_code=response.status_code
            ) from exc
        return TaskPage(items=items, total=total, next_offset=nxt)

    async def get_task(self, task_id: str) -> TaskState:
        """Public task state: status, current step and the sanitized execution trace (no internal reasoning)."""
        response = await self._request("GET", f"/api/tasks/{self._safe_id(task_id)}", retry=True)
        return self._parse(TaskState, response)

    async def get_runtime_metrics(self) -> RuntimeMetrics:
        """Admin-only operator metrics (durable task counts + process counters). Needs the operator credential."""
        response = await self._request("GET", "/api/admin/metrics", retry=True)
        return self._parse(RuntimeMetrics, response)

    async def get_result(self, task_id: str) -> TaskResult:
        response = await self._request("GET", f"/api/tasks/{self._safe_id(task_id)}/result", retry=True)
        return self._parse(TaskResult, response)

    async def approve(self, task_id: str) -> DecisionAck:
        response = await self._request("POST", f"/api/tasks/{self._safe_id(task_id)}/approve", retry=False)
        return self._parse(DecisionAck, response, outcome_unknown=True)

    async def reject(self, task_id: str, reason: str | None = None) -> DecisionAck:
        body = {"reason": reason[:500]} if reason else None
        response = await self._request(
            "POST", f"/api/tasks/{self._safe_id(task_id)}/reject", json_body=body or {}, retry=False
        )
        return self._parse(DecisionAck, response, outcome_unknown=True)

    async def cancel(self, task_id: str) -> DecisionAck:
        response = await self._request("POST", f"/api/tasks/{self._safe_id(task_id)}/cancel", retry=False)
        return self._parse(DecisionAck, response, outcome_unknown=True)

    @staticmethod
    def _safe_id(task_id: str) -> str:
        # Same alphabet DARIUS accepts; blocks path traversal before it leaves this process.
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task_id or ""):
            raise DariusNotFound("Not found", status_code=404)
        return task_id


# ---- wiring -----------------------------------------------------------------
_clients: dict[str, DariusClient] = {}


def _build(label: str, token: str) -> DariusClient:
    s = get_settings()
    return DariusClient(
        s.darius_base_url,
        token,
        timeout=s.darius_request_timeout_seconds,
        max_attempts=s.darius_request_max_attempts,
        backoff=s.darius_request_backoff_seconds,
        breaker=CircuitBreaker(s.darius_circuit_failure_threshold, s.darius_circuit_cooldown_seconds),
        label=label,
    )


def get_service_client() -> DariusClient:
    """Client that creates and reads this application's own tasks."""
    if "service" not in _clients:
        _clients["service"] = _build("service", get_settings().darius_api_token)
    return _clients["service"]


def get_operator_client() -> DariusClient:
    """Admin credential: human decisions and the cross-client operator view."""
    if "operator" not in _clients:
        _clients["operator"] = _build("operator", get_settings().darius_operator_token)
    return _clients["operator"]


def reset_clients() -> None:
    """Drops cached clients (tests, settings reload)."""
    _clients.clear()
