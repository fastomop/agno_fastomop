"""
Test database agent with verbose MCP tool inspection (integration).
"""

import pytest

from agno_fastomop.agents.database import create_database_agent


@pytest.mark.integration
async def test_database_agent_verbose(mcp_tools):
    """Build a database agent against a live MCP connection and inspect tools."""

    agent = create_database_agent(mcp_tools)

    # Tool surface is wired up
    assert hasattr(agent, "tools"), "agent should expose a `tools` attribute"
    assert agent.tools, "agent should have at least one tool wired (MCPTools)"

    query = "Execute this SQL: SELECT COUNT(*) FROM base.person"
    response = await agent.arun(query)

    assert response is not None
    assert response.content
    assert response.messages, "response should carry at least one message"
