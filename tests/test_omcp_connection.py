import asyncio
import os
import tomllib
from pathlib import Path
from dotenv import load_dotenv
from agno.tools.mcp import MCPTools

load_dotenv()


def _load_omcp_command_and_env() -> str:
    # Prefer MCP_COMMAND env var (set in .env), fall back to config.toml
    env_cmd = os.getenv("MCP_COMMAND", "").strip()
    if env_cmd:
        return env_cmd

    config_path = str(Path(__file__).resolve().parent.parent / "config.toml")
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    raw_cmd = cfg.get("omcp", {}).get("command", "").strip()
    if not raw_cmd:
        raise RuntimeError(
            "OMCP command not configured. Set MCP_COMMAND in .env or "
            "[omcp] command in config.toml"
        )
    # If the command starts with an env assignment like "DB_PATH=... ", move it to os.environ
    parts = raw_cmd.split(" ", 1)
    if "=" in parts[0]:
        key, _, value = parts[0].partition("=")
        if key and value:
            os.environ[key] = value
        cmd = parts[1] if len(parts) > 1 else ""
    else:
        cmd = raw_cmd
    if not cmd:
        raise RuntimeError("OMCP command is empty after parsing env assignment")
    return cmd


async def test_omcp_connection():
    command = _load_omcp_command_and_env()
    async with MCPTools(transport="stdio", command=command) as mcp_tools:
        print("Connected to OMCP server")
        print(f"MCP tools: {list(mcp_tools.functions.keys())}")

if __name__ == "__main__":
    asyncio.run(test_omcp_connection())
