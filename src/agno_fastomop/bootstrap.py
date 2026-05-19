import asyncio
from pathlib import Path

from agno_fastomop.config import validate_config
from agno_fastomop.observability.tracer import get_langfuse_client


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
            print(f"Error: Prompt file not found: {prompt_path}")
            return False

        prompt_content = prompt_path.read_text()

        try:
            # Create prompt with production label
            prompt = langfuse.create_prompt(
                name=prompt_name,
                prompt=prompt_content,
                labels=["dev"],
            )
            print(f"Prompt '{prompt_name}' uploaded to Langfuse (version: {prompt.version})")

        except Exception as e:
            print(f"Error uploading prompt {prompt_name}: {e}")
            # Try to continue with other prompts
            continue

    print("All prompts uploaded successfully")
    return True


async def main():
    validate_config()
    prompts_uploaded = bootstrap_prompts()

    if prompts_uploaded:
        print("Bootstrap completed successfully")
    else:
        print("Bootstrap failed")


if __name__ == "__main__":
    asyncio.run(main())
