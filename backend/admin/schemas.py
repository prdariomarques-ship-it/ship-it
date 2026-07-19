"""Response models for the admin dashboard (Sprint 4), plus one request model
(`UserAdminCreate`) added when public self-registration was closed.

Every response field here is either sourced directly from an existing
table/registry or explicitly nullable when the underlying data doesn't exist
yet (e.g. per-execution duration/tokens — see docs/DASHBOARD.md "Limitações
conhecidas"). Never include a token/secret/password field in a response
model — see `admin/service.py` module docstring for the exclusion list this
was checked against.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models.user import UserRole


class ComponentStatus(BaseModel):
    name: str
    online: bool
    detail: str = ""
    latency_ms: float | None = None
    last_heartbeat: datetime | None = None


class SystemInfo(BaseModel):
    app_name: str
    version: str
    environment: str
    commit: str | None
    branch: str | None
    tag: str | None
    uptime_seconds: float
    cpu_percent: float | None
    memory_used_mb: float | None
    memory_total_mb: float | None
    memory_percent: float | None
    disk_used_gb: float | None
    disk_total_gb: float | None
    disk_percent: float | None
    db_pool_size: int | None
    db_pool_checked_out: int | None
    # Provider *names* only (e.g. "openai", "openwa") — never a key/secret/token.
    llm_provider: str
    embedding_provider: str
    whatsapp_provider: str
    mail_provider: str
    calendar_provider: str
    contacts_provider: str
    drive_provider: str
    auto_reply_enabled: bool
    jobs_enabled: bool


class AgentAdminInfo(BaseModel):
    name: str
    description: str
    tool_count: int
    runs_total: int | None
    runs_ok: int | None
    runs_error: int | None
    avg_duration_seconds: float | None
    last_execution: datetime | None


class ToolAdminInfo(BaseModel):
    name: str
    description: str
    category: str
    agents: list[str]
    parameters: dict
    permissions: str | None  # not modeled on Tool today — always null, see docs
    calls_total: int | None
    calls_ok: int | None
    calls_error: int | None
    last_call: datetime | None  # not tracked per-tool today — always null, see docs


class GoogleAccountInfo(BaseModel):
    user_id: int
    label: str
    scopes: list[str]
    connected_at: datetime


class GoogleDomainStatus(BaseModel):
    domain: str
    connected_accounts: int
    accounts: list[GoogleAccountInfo]
    indexed_items: int | None = None  # only meaningful for Drive
    last_indexed_at: datetime | None = None  # only meaningful for Drive


class GoogleWorkspaceStatus(BaseModel):
    mail: GoogleDomainStatus
    calendar: GoogleDomainStatus
    contacts: GoogleDomainStatus
    drive: GoogleDomainStatus


class MemoryCollectionStats(BaseModel):
    name: str
    points_count: int | None
    vectors_count: int | None
    status: str | None


class MemoryStats(BaseModel):
    collection: MemoryCollectionStats
    embeddings_total: int
    embeddings_by_source: dict[str, int]
    drive_indexed_files: int
    drive_last_indexed_at: datetime | None
    cache_backend: str


class ExecutionEntry(BaseModel):
    """One row derived from an existing record (a `Job` or a `LogEntry`) —
    not a dedicated execution-audit table, which doesn't exist. See
    docs/DASHBOARD.md for why `agent`/`duration_seconds` are best-effort."""

    kind: str  # "job" | "log"
    id: int
    timestamp: datetime
    name: str
    agent: str | None
    status: str
    detail: str
    duration_seconds: float | None


class UserAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class UserAdminCreate(BaseModel):
    """Admin-only user creation — see `AuthService.create_user_as_admin`.
    The only way to add an account once the bootstrap admin exists, now
    that public `/auth/register` is closed after the first account."""

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.USER


class WhatsAppStatus(BaseModel):
    provider: str
    connected: bool
    detail: str
    queue_depth: int
    messages_sent: int
    messages_received: int


class AdminIndex(BaseModel):
    users_total: int
    agents_total: int
    tools_total: int
    google_connected_accounts: int
    whatsapp_connected: bool
    uptime_seconds: float


class ActionLogCreate(BaseModel):
    """One Action Center execution, submitted after the underlying write
    (task/goal/job/calendar endpoint) has already succeeded or failed —
    this call only records *why* it happened, it never performs the action
    itself. See ACTION_CENTER.md."""

    action_type: str
    category: str
    recommendation_title: str
    result: str  # "success" | "failure"
    related_entities: list[str] = []
    estimated_minutes: int | None = None
    detail: str | None = None


class ActionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
