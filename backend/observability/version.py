"""Release version metadata — reads the build-time VERSION.json (generated
by the release process, see RC1_AUDIT.md / RELEASE_NOTES.md) and exposes it
over HTTP. Read-only: this module never modifies application behavior,
only reports what release is currently running."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

from utils.config import get_settings

router = APIRouter(tags=["version"])

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION.json"


@lru_cache(maxsize=1)
def _read_version_file() -> dict:
    """Cached — VERSION.json is a build artifact, fixed for the life of
    the running process. Falls back to an honest "unknown" payload rather
    than failing the endpoint when running from source without a generated
    VERSION.json (e.g. local dev)."""
    try:
        return json.loads(_VERSION_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "version": "unknown",
            "commit": "unknown",
            "buildDate": None,
            "releaseType": "unknown",
        }


@router.get("/version")
async def version() -> dict:
    data = _read_version_file()
    return {
        "version": data.get("version", "unknown"),
        "commit": data.get("commit", "unknown"),
        "builtAt": data.get("buildDate"),
        "environment": get_settings().environment,
        "releaseType": data.get("releaseType", "unknown"),
    }
