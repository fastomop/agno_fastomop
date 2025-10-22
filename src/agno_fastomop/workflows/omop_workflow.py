from agno.workflow import Workflow, Step
from agno.tools.mcp import MCPTools
from agno_fastomop.agents.semantic import create_semantic_agent
from agno_fastomop.agents.database import create_database_agent
from agno_fastomop.config import config
from agno_fastomop.observability.trace_context import write_trace_context_otel, clear_trace_context
from langfuse import observe, Langfuse
import asyncio
import os

# Module-level storage for workflow (created once, reused)
_omop_workflow = None
_mcp_tools = None
_init_lock = asyncio.Lock()


async def initialize_workflow():
    """
    Initialize Workflow with semantic -> database pipeline.
    FastOMOP approach: ONE shared MCP connection for both agents.
    """
    global _omop_workflow, _mcp_tools

    async with _init_lock:
        if _omop_workflow is not None:
            return _omop_workflow

        # Create ONE MCP connection (shared by both agents to avoid DuckDB lock)
        # Pass Langfuse credentials to OMCP subprocess for trace propagation
        omcp_config = config["omcp"]
        _mcp_tools = MCPTools(
            transport=omcp_config["transport"],
            command=omcp_config["command"],
            env={
                "DB_PATH": os.getenv("DB_PATH", ""),
                "LANGFUSE_PUBLIC_KEY": os.getenv("LANGFUSE_PUBLIC_KEY", ""),
                "LANGFUSE_SECRET_KEY": os.getenv("LANGFUSE_SECRET_KEY", ""),
                "LANGFUSE_HOST": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            }
        )

        # Manually connect MCP once
        await _mcp_tools._connect()

        # Create agents with shared MCP - both query the database
        semantic_agent = create_semantic_agent(_mcp_tools)  # Queries concept table
        database_agent = create_database_agent(_mcp_tools)  # Generates & executes SQL

        # Create linear workflow (supports structured output passing)
        _omop_workflow = Workflow(
            name="OMOP Clinical Query Workflow",
            steps=[
                Step(
                    name="Semantic Extraction",
                    agent=semantic_agent,
                    description="Extract clinical concepts and map to OMOP codes",
                ),
                Step(
                    name="SQL Generation and Execution",
                    agent=database_agent,
                    description="Generate SQL from semantic context and execute",
                ),
            ],
        )

        return _omop_workflow


@observe() #Complete langfuse tracing
async def run_omop_query(user_query: str) -> str:
    """
    Run OMOP clinical query via Workflow
    Initializes on first call, reuses for subsequent queries
    """
    # Inject current OpenTelemetry trace context for OMCP subprocess
    # This uses W3C Trace Context format (traceparent/tracestate)
    try:
        write_trace_context_otel()
    except Exception as e:
        # Non-critical: if trace context extraction fails, continue without it
        print(f"Warning: Could not inject OpenTelemetry trace context: {e}")

    workflow = await initialize_workflow()
    response = await workflow.arun(user_query)
    return response


async def cleanup_workflow():
    """
    Cleanup resources (call on shutdown)
    Closes MCP connection
    """
    global _omop_workflow

    if _omop_workflow is not None and hasattr(_omop_workflow, 'steps'):
        for step in _omop_workflow.steps:
            if hasattr(step.agent, 'tools'):
                for tool in step.agent.tools:
                    if hasattr(tool, 'close'):
                        await tool.close()


    langfuse = Langfuse()
    langfuse.flush()