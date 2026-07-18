"""Release version metadata — reads the build-time VERSION.json (generated
by the release process, see RC1_AUDIT.md / RELEASE_NOTES.md) and exposes it
over HTTP. Read-only: this module never modifies application behavior,
only reports what release is currently running."""

from fastapi import APIRouter

from utils.config import get_settings
from utils.version_file import read_version_file

router = APIRouter(tags=["version"])


@router.get("/version")
async def version() -> dict:
    data = read_version_file()
    return {
        "version": data.get("version", "unknown"),
        "commit": data.get("commit", "unknown"),
        "builtAt": data.get("buildDate"),
        "environment": get_settings().environment,
        "releaseType": data.get("releaseType", "unknown"),
    }
