"""Notes: CRUD, search (title/content/tags, case-insensitive, partial),
pinned/archived organization, ownership isolation and input validation.
"""

import pytest


@pytest.fixture
async def other_auth_headers(client, auth_headers) -> dict[str, str]:
    """Depends on `auth_headers` so the admin account always registers
    first -- public registration is closed after that (see test_auth.py),
    so this second, non-admin account must be created via the admin
    endpoint using the admin's own token."""
    await client.post(
        "/api/admin/users",
        json={
            "email": "other-notes@example.com",
            "full_name": "Other",
            "password": "supersecret1",
        },
        headers=auth_headers,
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "other-notes@example.com", "password": "supersecret1"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- CRUD ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_and_get_note(client, auth_headers):
    created = await client.post(
        "/api/notes",
        json={"title": "Ideia", "content": "Automatizar avisos", "tags": ["igreja"]},
        headers=auth_headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Ideia"
    assert body["pinned"] is False
    assert body["archived"] is False
    assert body["contact_id"] is None

    fetched = await client.get(f"/api/notes/{body['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Ideia"


@pytest.mark.asyncio
async def test_update_note(client, auth_headers):
    created = await client.post(
        "/api/notes", json={"title": "Original"}, headers=auth_headers
    )
    note_id = created.json()["id"]

    updated = await client.patch(
        f"/api/notes/{note_id}",
        json={"title": "Editado", "pinned": True},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "Editado"
    assert body["pinned"] is True


@pytest.mark.asyncio
async def test_update_note_only_touches_sent_fields(client, auth_headers):
    created = await client.post(
        "/api/notes",
        json={"title": "X", "content": "Conteúdo original"},
        headers=auth_headers,
    )
    note_id = created.json()["id"]

    updated = await client.patch(
        f"/api/notes/{note_id}", json={"title": "Y"}, headers=auth_headers
    )
    assert updated.json()["content"] == "Conteúdo original"


@pytest.mark.asyncio
async def test_delete_note(client, auth_headers):
    created = await client.post(
        "/api/notes", json={"title": "Apagar"}, headers=auth_headers
    )
    note_id = created.json()["id"]

    deleted = await client.delete(f"/api/notes/{note_id}", headers=auth_headers)
    assert deleted.status_code == 204
    assert (
        await client.get(f"/api/notes/{note_id}", headers=auth_headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_count_notes(client, auth_headers):
    await client.post("/api/notes", json={"title": "A"}, headers=auth_headers)
    await client.post("/api/notes", json={"title": "B"}, headers=auth_headers)

    count = await client.get("/api/notes/count", headers=auth_headers)
    assert count.json() == {"count": 2}


# --- Validation ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_note_rejects_empty_title(client, auth_headers):
    response = await client.post(
        "/api/notes", json={"title": ""}, headers=auth_headers
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_note_requires_title_field(client, auth_headers):
    response = await client.post("/api/notes", json={}, headers=auth_headers)
    assert response.status_code == 422


# --- Ownership / RBAC --------------------------------------------------------------
@pytest.mark.asyncio
async def test_note_cross_user_isolation_on_get(
    client, auth_headers, other_auth_headers
):
    created = await client.post(
        "/api/notes", json={"title": "Minha nota"}, headers=auth_headers
    )
    note_id = created.json()["id"]

    response = await client.get(f"/api/notes/{note_id}", headers=other_auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_note_cross_user_isolation_on_update(
    client, auth_headers, other_auth_headers
):
    created = await client.post(
        "/api/notes", json={"title": "Minha nota"}, headers=auth_headers
    )
    note_id = created.json()["id"]

    response = await client.patch(
        f"/api/notes/{note_id}",
        json={"title": "Sequestrada"},
        headers=other_auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_note_cross_user_isolation_on_delete(
    client, auth_headers, other_auth_headers
):
    created = await client.post(
        "/api/notes", json={"title": "Minha nota"}, headers=auth_headers
    )
    note_id = created.json()["id"]

    response = await client.delete(
        f"/api/notes/{note_id}", headers=other_auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_note_list_only_shows_own_notes(
    client, auth_headers, other_auth_headers
):
    await client.post("/api/notes", json={"title": "Minha"}, headers=auth_headers)
    await client.post(
        "/api/notes", json={"title": "Da outra pessoa"}, headers=other_auth_headers
    )

    mine = await client.get("/api/notes", headers=auth_headers)
    titles = [note["title"] for note in mine.json()]
    assert titles == ["Minha"]


@pytest.mark.asyncio
async def test_notes_endpoints_require_authentication(client):
    assert (await client.get("/api/notes")).status_code == 401
    assert (await client.post("/api/notes", json={"title": "X"})).status_code == 401


# --- Search ------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_matches_title_case_insensitive_partial(client, auth_headers):
    await client.post(
        "/api/notes", json={"title": "Reunião de Orçamento"}, headers=auth_headers
    )
    await client.post("/api/notes", json={"title": "Lista de compras"}, headers=auth_headers)

    response = await client.get("/api/notes?q=orçamento", headers=auth_headers)
    titles = [note["title"] for note in response.json()]
    assert titles == ["Reunião de Orçamento"]


@pytest.mark.asyncio
async def test_search_matches_content(client, auth_headers):
    await client.post(
        "/api/notes",
        json={"title": "X", "content": "Falar com o João sobre o projeto"},
        headers=auth_headers,
    )
    await client.post("/api/notes", json={"title": "Y", "content": "Nada a ver"}, headers=auth_headers)

    response = await client.get("/api/notes?q=joão", headers=auth_headers)
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "X"


@pytest.mark.asyncio
async def test_search_matches_tags(client, auth_headers):
    await client.post(
        "/api/notes", json={"title": "X", "tags": ["Trabalho", "Urgente"]}, headers=auth_headers
    )
    await client.post("/api/notes", json={"title": "Y", "tags": ["Pessoal"]}, headers=auth_headers)

    response = await client.get("/api/notes?q=urgente", headers=auth_headers)
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "X"


@pytest.mark.asyncio
async def test_search_with_no_query_returns_everything(client, auth_headers):
    await client.post("/api/notes", json={"title": "A"}, headers=auth_headers)
    await client.post("/api/notes", json={"title": "B"}, headers=auth_headers)

    response = await client.get("/api/notes", headers=auth_headers)
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_search_with_no_matches_returns_empty_list(client, auth_headers):
    await client.post("/api/notes", json={"title": "A"}, headers=auth_headers)

    response = await client.get("/api/notes?q=inexistente", headers=auth_headers)
    assert response.json() == []


# --- Pinned / archived ordering and filtering --------------------------------------
@pytest.mark.asyncio
async def test_pinned_notes_sort_first(client, auth_headers):
    await client.post("/api/notes", json={"title": "Normal"}, headers=auth_headers)
    pinned = await client.post(
        "/api/notes", json={"title": "Fixada", "pinned": True}, headers=auth_headers
    )
    assert pinned.status_code == 201

    response = await client.get("/api/notes", headers=auth_headers)
    titles = [note["title"] for note in response.json()]
    assert titles[0] == "Fixada"


@pytest.mark.asyncio
async def test_archived_notes_hidden_by_default(client, auth_headers):
    created = await client.post(
        "/api/notes", json={"title": "Antiga"}, headers=auth_headers
    )
    note_id = created.json()["id"]
    await client.patch(
        f"/api/notes/{note_id}", json={"archived": True}, headers=auth_headers
    )

    default_list = await client.get("/api/notes", headers=auth_headers)
    assert default_list.json() == []

    with_archived = await client.get(
        "/api/notes?include_archived=true", headers=auth_headers
    )
    assert len(with_archived.json()) == 1
    assert with_archived.json()[0]["archived"] is True
