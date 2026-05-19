"""Shared pytest fixtures and configuration.

The `integration` marker is declared in `pyproject.toml`. Tests using it are
skipped by default in CI; run them locally with `uv run pytest -m integration`.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from agno.tools.mcp import MCPTools

from agno_fastomop.config import config

# Env vars required for any integration test that talks to the OMCP MCP
# server. When unset, integration tests are skipped rather than crashing
# inside the agno MCP guard (which rejects unexpanded `${...}` placeholders).
_INTEGRATION_ENV_VARS = ("OMCP_SERVER_DIR", "DB_PATH")


@pytest.fixture(autouse=True)
def _skip_integration_if_env_missing(request: pytest.FixtureRequest) -> None:
    """Auto-skip integration tests when the required env vars aren't set."""
    if "integration" not in request.keywords:
        return
    missing = [name for name in _INTEGRATION_ENV_VARS if not os.getenv(name)]
    if missing:
        pytest.skip(f"integration test skipped: missing env var(s) {', '.join(missing)}")


@pytest_asyncio.fixture
async def mcp_tools():
    """Yield a connected `MCPTools` instance for integration tests.

    Uses the OMCP command template from `config.toml`, expanding any
    `${OMCP_SERVER_DIR}` placeholder against the current environment, and
    honouring an explicit `MCP_COMMAND` override.
    """
    omcp_config = config["omcp"]
    command = os.getenv("MCP_COMMAND", os.path.expandvars(omcp_config["command"]))
    async with MCPTools(
        transport=omcp_config["transport"],
        command=command,
        env={"DB_PATH": os.getenv("DB_PATH", "")},
    ) as tools:
        yield tools
