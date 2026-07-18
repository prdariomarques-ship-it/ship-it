from unittest.mock import patch

import pytest

from utils.version_file import read_version_file


@pytest.mark.asyncio
async def test_version_returns_real_build_metadata(client):
    read_version_file.cache_clear()
    response = await client.get("/api/version")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "1.3.1"
    assert len(body["commit"]) == 40  # full git SHA
    assert body["releaseType"] == "patch"
    assert body["environment"] == "test"
    assert body["builtAt"] is not None


@pytest.mark.asyncio
async def test_version_endpoint_requires_no_authentication(client):
    """Version metadata is safe to expose publicly, like /health."""
    response = await client.get("/api/version")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_version_falls_back_honestly_when_file_missing(client, tmp_path):
    read_version_file.cache_clear()
    with patch("utils.version_file._VERSION_FILE", tmp_path / "does-not-exist.json"):
        response = await client.get("/api/version")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "unknown"
    assert body["commit"] == "unknown"
    assert body["builtAt"] is None
    assert body["releaseType"] == "unknown"
    read_version_file.cache_clear()
