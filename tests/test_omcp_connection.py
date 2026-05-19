"""Smoke-test the OMCP MCP server connection (integration)."""

import os
import tomllib
from pathlib import Path

import pytest
from agno.tools.mcp import MCPTools


def _load_omcp_command() -> str:
    config_path = Path(__file__).resolve().parent.parent / "config.toml"
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    raw_cmd = cfg.get("omcp", {}).get("command", "").strip()
    if not raw_cmd:
        raise RuntimeError("OMCP command not found in config.toml")
    return os.path.expandvars(raw_cmd)


@pytest.mark.integration
async def test_omcp_connection():
    command = _load_omcp_command()
    async with MCPTools(transport="stdio", command=command) as mcp_tools:
        print("Connected to OMCP server")
        print(f"MCP tools: {list(mcp_tools.functions.keys())}")
