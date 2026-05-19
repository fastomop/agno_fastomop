"""
Query patient count via OMCP MCP server (integration).
"""

import os

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.integration
async def test_patient_count():
    """Test MCP connection and query patient count"""

    omcp_dir = os.environ["OMCP_SERVER_DIR"]
    db_path = os.environ["DB_PATH"]

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "--directory", omcp_dir, "python", "src/omcp/main.py"],
        env={"DB_PATH": db_path},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("Connected to OMCP server")
            print("=" * 50)

            # Query patient count
            sql_query = "SELECT COUNT(*) as patient_count FROM base.person"

            result = await session.call_tool("Select_Query", arguments={"query": sql_query})

            print(f"SQL Query: {sql_query}")
            print("=" * 50)
            print("Result:")
            print(result.content[0].text)
            print("=" * 50)
