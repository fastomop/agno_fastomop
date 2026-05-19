"""
Test database agent standalone (integration — requires OMCP + DB + LLM).
"""

import pytest

from agno_fastomop.agents.database import create_database_agent


@pytest.mark.integration
async def test_database_agent(mcp_tools):
    """Test database agent for SQL generation and execution."""

    agent = create_database_agent(mcp_tools)

    query = "Execute SQL: SELECT COUNT(*) FROM base.person"
    response = await agent.arun(query)

    assert response is not None
    assert response.content
