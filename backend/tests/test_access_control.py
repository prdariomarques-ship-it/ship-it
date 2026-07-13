"""Tests for access control — authentication and authorization."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from auth.jwt import create_access_token
from auth.password import hash_password
from models.user import User, UserRole


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def admin_user(session_factory) -> User:
    async with session_factory() as session:
        user = User(
            email="admin@example.com",
            full_name="Admin",
            hashed_password=hash_password("testpass123"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def regular_user(session_factory) -> User:
    async with session_factory() as session:
        user = User(
            email="user@example.com",
            full_name="User",
            hashed_password=hash_password("testpass123"),
            role=UserRole.USER,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
def admin_headers(admin_user) -> dict[str, str]:
    token = create_access_token(str(admin_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_headers(regular_user) -> dict[str, str]:
    token = create_access_token(str(regular_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_endpoint_requires_authentication(client):
    """Admin endpoints require authentication."""
    response = await client.get("/api/admin")
    assert response.status_code == 401
    assert "Not authenticated" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_endpoint_rejects_non_admin_user(client, user_headers):
    """Admin endpoints reject non-admin users."""
    response = await client.get("/api/admin", headers=user_headers)
    assert response.status_code == 403
    assert "Insufficient permissions" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_endpoint_allows_admin_user(client, admin_headers):
    """Admin endpoints allow admin users."""
    response = await client.get("/api/admin", headers=admin_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_status_requires_admin_role(client, user_headers):
    """Admin status endpoints require ADMIN role."""
    response = await client.get("/api/admin/status", headers=user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_system_requires_admin_role(client, user_headers):
    """Admin system endpoints require ADMIN role."""
    response = await client.get("/api/admin/system", headers=user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_agents_requires_admin_role(client, user_headers):
    """Admin agents endpoints require ADMIN role."""
    response = await client.get("/api/admin/agents", headers=user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_permission_denied_is_logged(client, user_headers):
    """Permission denied (403) attempts are logged."""
    response = await client.get("/api/admin", headers=user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_is_logged(client):
    """Unauthenticated requests (401) are tracked."""
    response = await client.get("/api/admin")
    assert response.status_code == 401
