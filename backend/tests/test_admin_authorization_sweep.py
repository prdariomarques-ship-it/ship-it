"""Authorization sweep: EVERY route under /api/admin must refuse anonymous and non-admin callers.

Enumerating the router (instead of listing endpoints by hand) means a route added later without
`require_admin` fails here, not in production. The probe only needs the auth dependency to run first:
a refused call must not reach any handler, so nothing is written.
"""
from __future__ import annotations

import re

import pytest

from main import app
from tests.test_admin_darius import admin_user, session_factory, user_headers  # noqa: F401

_PARAM = re.compile(r"\{[^}]+\}")
PROBE_BODY = {"reason": "x", "suspended": True}


def _admin_routes() -> list[tuple[str, str]]:
    # The OpenAPI document is the one view that does not depend on how this FastAPI version wraps included routers.
    pairs: list[tuple[str, str]] = []
    for path, operations in app.openapi()["paths"].items():
        if path.startswith("/api/admin"):
            for method in operations:
                if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                    pairs.append((method.upper(), _PARAM.sub("1", path)))
    return sorted(pairs)


ROUTES = _admin_routes()


def test_the_sweep_actually_sees_the_admin_surface():
    paths = {path for _method, path in ROUTES}
    for expected in (
        "/api/admin/darius/status",
        "/api/admin/darius/metrics",
        "/api/admin/darius/paused-conversations",
        "/api/admin/darius/tasks/1/approve",
        "/api/admin/automation/suspension/global",
    ):
        assert expected in paths
    assert len(ROUTES) >= 20  # a sweep over a handful of routes would prove little


@pytest.mark.parametrize("method,path", ROUTES)
async def test_anonymous_is_refused(client, method, path):
    response = await client.request(method, path, json=PROBE_BODY if method != "GET" else None)
    assert response.status_code in (401, 403), f"{method} {path} answered {response.status_code} without credentials"


@pytest.mark.parametrize("method,path", ROUTES)
async def test_a_regular_user_is_refused(client, user_headers, method, path):  # noqa: F811
    response = await client.request(
        method, path, headers=user_headers, json=PROBE_BODY if method != "GET" else None
    )
    assert response.status_code == 403, f"{method} {path} answered {response.status_code} to a non-admin"
