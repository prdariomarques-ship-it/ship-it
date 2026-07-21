"""Name search on /contacts and /church/members (repository_cls wiring in
api/crud.py's generic factory) -- both already had `search_by_name` on
their specialized repositories; this only exposes it via `?q=`.
"""

import pytest


@pytest.mark.asyncio
async def test_contacts_search_matches_name_case_insensitive_partial(
    client, auth_headers
):
    await client.post(
        "/api/contacts", json={"name": "João Silva", "phone": "5511911111111"},
        headers=auth_headers,
    )
    await client.post(
        "/api/contacts", json={"name": "Maria Souza", "phone": "5511922222222"},
        headers=auth_headers,
    )

    response = await client.get("/api/contacts?q=joão", headers=auth_headers)
    assert response.status_code == 200
    names = [contact["name"] for contact in response.json()]
    assert names == ["João Silva"]


@pytest.mark.asyncio
async def test_contacts_without_query_returns_full_list(client, auth_headers):
    await client.post(
        "/api/contacts", json={"name": "A", "phone": "5511911111111"},
        headers=auth_headers,
    )
    await client.post(
        "/api/contacts", json={"name": "B", "phone": "5511922222222"},
        headers=auth_headers,
    )

    response = await client.get("/api/contacts", headers=auth_headers)
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_contacts_search_with_no_match_returns_empty_list(client, auth_headers):
    await client.post(
        "/api/contacts", json={"name": "A", "phone": "5511911111111"},
        headers=auth_headers,
    )

    response = await client.get("/api/contacts?q=inexistente", headers=auth_headers)
    assert response.json() == []


@pytest.mark.asyncio
async def test_church_members_search_matches_name(client, auth_headers):
    await client.post(
        "/api/church/members", json={"name": "Pedro Alves", "role": "louvor"},
        headers=auth_headers,
    )
    await client.post(
        "/api/church/members", json={"name": "Ana Costa", "role": "recepção"},
        headers=auth_headers,
    )

    response = await client.get("/api/church/members?q=alves", headers=auth_headers)
    assert response.status_code == 200
    names = [member["name"] for member in response.json()]
    assert names == ["Pedro Alves"]


@pytest.mark.asyncio
async def test_church_members_without_query_returns_full_list(client, auth_headers):
    await client.post(
        "/api/church/members", json={"name": "A", "role": "x"}, headers=auth_headers
    )
    await client.post(
        "/api/church/members", json={"name": "B", "role": "y"}, headers=auth_headers
    )

    response = await client.get("/api/church/members", headers=auth_headers)
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_tasks_ignores_an_unsupported_q_param(client, auth_headers):
    """tasks_router has no search_by_name -- `q` isn't a real parameter for
    it, so an unrecognized query string must not break the endpoint."""
    await client.post(
        "/api/tasks", json={"title": "Preparar culto"}, headers=auth_headers
    )

    response = await client.get("/api/tasks?q=whatever", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
