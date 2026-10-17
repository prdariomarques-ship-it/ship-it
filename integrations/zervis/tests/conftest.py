import pytest

from zervis_bridge.config import Settings

DARIOOS_TOKEN = "d" * 32
MCP_TOKEN = "m" * 32


@pytest.fixture
def settings() -> Settings:
    return Settings(
        darioos_token=DARIOOS_TOKEN,
        mcp_token=MCP_TOKEN,
        request_backoff_seconds=0,
        allowed_hosts=["bridge"],
    )
