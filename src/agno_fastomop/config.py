import os
from pathlib import Path
from dotenv import load_dotenv
import tomli
from typing import Dict, Any

load_dotenv()

#Project config
CONFIG_PATH = Path(__file__).parent.parent.parent / "config.toml"

def load_config() -> dict:
    """
    Load config
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found at {CONFIG_PATH}")
    
    with open(CONFIG_PATH, "rb") as f:
        return tomli.load(f)

config = load_config()

def get_agent_config(agent_name:str) -> Dict[str, Any]:
    """
    Get agent config
    """
    if agent_name not in config["agents"]:
        raise ValueError(f"Agent name {agent_name} not found in config")
    
    agent_config = config["agents"][agent_name].copy()

    #Provider
    provider = agent_config.get("model_provider", config["models"]["default_provider"])
    provider_config = config["models"]["providers"][provider].copy()

    complete_config = {
        **agent_config,
        "MODEL_TYPE": provider_config["provider"],
        "MODEL_ID": provider_config["model_id"],
        "MCP_COMMAND": os.getenv("MCP_COMMAND", config["omcp"]["command"]),
    }

    #Add azure specifics
    if provider == "azure":
        complete_config["api_version"] = provider_config.get("api_version", "2024-10-21")

    return complete_config


def validate_config():
    """
    Validate required environment variables based on providers used.
    """
    required_base = [
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY"
    ]

    providers_used = set()
    for agent in config["agents"].values():
        provider = agent.get("model_provider", config["models"]["default_provider"])
        providers_used.add(provider)

    required_env = required_base.copy()

    if "azure" in providers_used:
        required_env.append("AZURE_OPENAI_API_KEY")
        required_env.append("AZURE_OPENAI_ENDPOINT")
        required_env.append("AZURE_OPENAI_DEPLOYMENT")

    if "openai" in providers_used:
        required_env.append("OPENAI_API_KEY")

    if "ollama" in providers_used:
        required_env.append("OLLAMA_HOST")

    if "anthropic" in providers_used:
        required_env.append("ANTHROPIC_API_KEY")

    missing = [var for var in required_env if not os.getenv(var)]

    if missing: 
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

validate_config()


    