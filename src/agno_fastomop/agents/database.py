import logging
from pathlib import Path

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.tools.mcp import MCPTools

from agno_fastomop.agents.factory import create_model
from agno_fastomop.config import get_agent_config
from agno_fastomop.observability.tracer import get_langfuse_client

logger = logging.getLogger(__name__)


def create_database_agent(mcp_tools: MCPTools) -> Agent:
    """
    Create omop database agent with shared MCP connection

    Args:
        mcp_tools: Shared MCP connection (to avoid DB lock conflicts)

    Returns:
        Agent: Agno agent for omop db queries
    """

    agent_config = get_agent_config("database")
    model = create_model(agent_config)
    db = SqliteDb(db_file="db_agent.db")

    # Fetch prompt from Langfuse
    try:
        langfuse = get_langfuse_client()
        prompt = langfuse.get_prompt("database_agent", label="dev")
        system_prompt = prompt.prompt
        logger.info("Loaded database_agent prompt from Langfuse (version: %s)", prompt.version)
    except Exception:
        logger.warning("Failed to load prompt from Langfuse; falling back to local prompt file", exc_info=True)
        prompt_path = Path(__file__).parent.parent / "prompts" / "database_agent.txt"
        with open(prompt_path, "r") as f:
            system_prompt = f.read()

    # Create agent with connected MCP tools
    agent = Agent(
        name=agent_config["name"],
        model=model,
        instructions=system_prompt,
        db=db,
        enable_user_memories=True,
        add_history_to_context=True,  # Enable conversation history
        tools=[mcp_tools],
        # No input_schema - the workflow passes previous step output as message content
        # No output_schema - return natural language for final answer
        # session_state only for JSON-serializable data
        session_state={
            "agent_type": "database_agent",
        },
        reasoning=agent_config.get("reasoning", True),
        markdown=agent_config.get("markdown", True),
    )

    return agent
