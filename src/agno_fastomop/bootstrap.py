import logging
from pathlib import Path

from agno_fastomop._logging import setup_logging
from agno_fastomop.config import validate_config
from agno_fastomop.observability.tracer import get_langfuse_client

logger = logging.getLogger(__name__)


def bootstrap_prompts():
    """Upload prompts to langfuse"""

    langfuse = get_langfuse_client()
    prompts_dir = Path(__file__).parent / "prompts"

    required_prompts = [
        ("database_agent", "database_agent.txt"),
        ("semantic_agent", "semantic_agent_fastomop.txt"),
        ("supervisor", "supervisor.txt"),
    ]

    for prompt_name, file_name in required_prompts:
        prompt_path = prompts_dir / file_name

        if not prompt_path.exists():
            logger.error("Prompt file not found: %s", prompt_path)
            return False

        prompt_content = prompt_path.read_text()

        try:
            # Create prompt with production label
            prompt = langfuse.create_prompt(
                name=prompt_name,
                prompt=prompt_content,
                labels=["dev"],
            )
            logger.info("Prompt '%s' uploaded to Langfuse (version: %s)", prompt_name, prompt.version)

        except Exception:
            logger.exception("Error uploading prompt %s", prompt_name)
            # Try to continue with other prompts
            continue

    logger.info("All prompts uploaded successfully")
    return True


async def main():
    setup_logging()
    validate_config()
    prompts_uploaded = bootstrap_prompts()

    if prompts_uploaded:
        logger.info("Bootstrap completed successfully")
    else:
        logger.error("Bootstrap failed")
