"""FastOMOP command-line entry point.

This module wires the three operational entry points behind a single Typer
application so users invoke them as::

    agno_fastomop bootstrap
    agno_fastomop run [--batch FILE] [--output FILE]
    agno_fastomop web

instead of the older ``uv run python -m agno_fastomop.<module>`` form.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import typer

from agno_fastomop import bootstrap as bootstrap_module
from agno_fastomop import run_agent as run_agent_module
from agno_fastomop import web_interface as web_interface_module
from agno_fastomop._logging import setup_logging
from agno_fastomop.config import validate_config

app = typer.Typer(
    name="agno_fastomop",
    help="FastOMOP — natural language to OMOP CDM SQL.",
    no_args_is_help=True,
    add_completion=False,
)


def _configure(log_level: Optional[str]) -> None:
    """Apply the optional --log-level override, then validate env config."""
    setup_logging(level=log_level.upper() if log_level else None)
    validate_config()


@app.command()
def bootstrap(
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Override LOG_LEVEL (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
        case_sensitive=False,
    ),
) -> None:
    """Upload agent prompts to Langfuse."""
    _configure(log_level)
    asyncio.run(bootstrap_module.main())


@app.command()
def run(
    batch: Optional[str] = typer.Option(
        None,
        "--batch",
        help="Path to JSON file containing queries for batch processing.",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        help="Path to save batch results JSON (defaults next to the batch file).",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Override LOG_LEVEL (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
        case_sensitive=False,
    ),
) -> None:
    """Run the OMOP query workflow interactively or in batch mode."""
    _configure(log_level)
    if batch:
        asyncio.run(run_agent_module.batch_mode(batch, output))
    else:
        asyncio.run(run_agent_module.interactive_session())


@app.command()
def web(
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Override LOG_LEVEL (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
        case_sensitive=False,
    ),
) -> None:
    """Start the FastOMOP web interface (AgentOS + uvicorn on port 7777)."""
    _configure(log_level)
    asyncio.run(web_interface_module.main())


if __name__ == "__main__":
    app()
