"""Scoped (limited) access tokens: what a scope may reach, fail-closed.

A scoped token is signed for the instance owner (Release 1.x is single-
operator, see docs/adr/ADR-0002) but may only perform the requests its scope
explicitly allows. The policy is deny-by-default and enforced in one place --
`auth.dependencies.get_current_user`, which every authenticated route already
goes through -- so a new router can never accidentally widen a scope.

`READ_SCOPE` is the only scope today: safe methods (GET/HEAD) on an explicit
allowlist of paths. It is meant for trusted read-only integrations (the Zérvis
MCP bridge, docs/adr/ADR-0003). It deliberately excludes anything that can
leak secrets or PII in bulk (`/admin/logs`, `/admin/users`, `/admin/settings`,
`/admin/whatsapp`, ...) and anything that can act (every non-GET request,
including `POST /agents/{name}/run`).
"""

import re
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request, status

from utils.config import get_settings

READ_SCOPE = "darioos:read"

_SAFE_METHODS = frozenset({"GET", "HEAD"})

# Paths are relative to `settings.api_prefix`. Each entry is full-matched
# (trailing slash ignored), never prefix-matched: allowing "/goals" must not
# allow "/goals/anything-added-later".
_READ_PATHS: tuple[str, ...] = (
    r"/agents",
    r"/agents/tools",
    r"/admin/status",
    r"/admin/agents",
    r"/admin/tools",
    r"/admin/executions",
    r"/admin/observation",
    r"/goals",
    r"/goals/ready",
    r"/goals/\d+",
    r"/tasks",
    r"/tasks/\d+",
)

_POLICIES: Mapping[str, tuple[str, ...]] = {READ_SCOPE: _READ_PATHS}


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def scoped_token_revoked(claims: Mapping[str, Any]) -> bool:
    """True when the token was issued before the configured kill-switch time."""
    revoked_before = get_settings().scoped_token_revoked_before
    if revoked_before <= 0:
        return False
    issued_at = claims.get("iat")
    return not isinstance(issued_at, int | float) or issued_at < revoked_before


def enforce_scoped_access(claims: Mapping[str, Any], request: Request) -> None:
    """Raise 403 unless `request` is within the scope carried by `claims`.

    Unknown scopes get no access at all, so a typo or a scope removed in a
    later release degrades to "nothing allowed", never to "everything".
    """
    scope = claims.get("scope")
    allowed_paths = _POLICIES.get(scope) if isinstance(scope, str) else None
    if allowed_paths is None:
        raise _forbidden("Unknown token scope")

    if request.method not in _SAFE_METHODS:
        raise _forbidden("Token scope is read-only")

    prefix = get_settings().api_prefix.rstrip("/")
    path = request.url.path.rstrip("/") or "/"
    if not any(re.fullmatch(prefix + pattern, path) for pattern in allowed_paths):
        raise _forbidden("Path not allowed for this token scope")
