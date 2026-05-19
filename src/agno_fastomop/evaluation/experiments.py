"""
Langfuse Dataset Evaluation for FastOMOP
Runs the agentic pipeline (run_agent) on Langfuse datasets
"""

import asyncio
import logging
from datetime import datetime

import nest_asyncio
from langfuse import Langfuse

from agno_fastomop._logging import setup_logging
from agno_fastomop.observability.tracer import get_langfuse_client
from agno_fastomop.workflows.omop_workflow import run_omop_query

logger = logging.getLogger(__name__)

# Allow nested event loops
nest_asyncio.apply()


def omop_task(item):
    """
    Task function for Langfuse dataset evaluation

    Args:
        item: Langfuse dataset item with 'input' field containing the query

    Returns:
        str: The agent's response
    """
    # Extract query from the dataset item
    # Handle nested input structure: item.input["input"]
    if isinstance(item.input, dict) and "input" in item.input:
        user_query = item.input["input"]
    else:
        user_query = item.input

    logger.info("Processing query: %s...", user_query[:100])

    try:
        # Run the async OMOP query workflow
        response = asyncio.run(run_omop_query(user_query))

        logger.info("Query completed: %s...", user_query[:50])
        return response

    except Exception as e:
        logger.exception("Error processing query")
        return f"Error processing query: {e}"


def run_experiment(
    dataset_name: str = "foem",
    experiment_name: str = "FastOMOP Agentic Pipeline",
    experiment_description: str = None,
    max_concurrency: int = 2,
):
    """
    Run a Langfuse dataset experiment

    Args:
        dataset_name: Name of the Langfuse dataset (default: "foem")
        experiment_name: Name for this experiment run
        experiment_description: Optional description for the experiment
        max_concurrency: Maximum number of concurrent queries to process (default: 2)
    """
    # Get Langfuse client
    langfuse = get_langfuse_client()

    # Get dataset from Langfuse
    logger.info("Loading dataset '%s' from Langfuse...", dataset_name)
    dataset = langfuse.get_dataset(dataset_name, fetch_items_page_size=100)
    logger.info("Dataset loaded with %d items", len(dataset.items))

    # Debug: Check if we need to fetch more items
    if hasattr(dataset, "meta"):
        logger.debug("Dataset metadata: %s", dataset.meta)

    # Run experiment on the dataset
    logger.info("Running experiment: %s", experiment_name)

    # Create custom run name with formatted timestamp
    timestamp = datetime.now().strftime("%Y/%m/%d-%H:%M:%S")
    run_name = f"{experiment_name} - {timestamp}"

    result = dataset.run_experiment(
        name=experiment_name,
        run_name=run_name,
        description=experiment_description or f"Evaluation of FastOMOP agentic pipeline on {dataset_name}",
        task=omop_task,
        max_concurrency=max_concurrency,
    )

    # Flush Langfuse traces
    logger.info("Flushing Langfuse traces...")
    langfuse = Langfuse()
    langfuse.flush()
    logger.info("Langfuse traces flushed")

    # Print formatted results to stdout — this is a human-readable
    # experiment summary, not diagnostic output.
    print("\n" + "=" * 60)
    print("EXPERIMENT RESULTS")
    print("=" * 60)
    print(result.format())

    return result


if __name__ == "__main__":
    setup_logging()
    # Run experiment on the "foem" dataset
    result = run_experiment(
        dataset_name="complete_foem",
        experiment_name="complete_foem test",
        experiment_description="Testing the complete agentic workflow on FOEM dataset",
        max_concurrency=1,  # Limit the concurrent queries (adjust as needed)
    )
