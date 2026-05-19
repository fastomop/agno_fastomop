import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from agno_fastomop.workflows.omop_workflow import cleanup_workflow, run_omop_query

logger = logging.getLogger(__name__)

# REPL banners use plain print() rather than the logger — they are interactive
# UI for the user at the terminal, not diagnostic output that should be
# filtered by LOG_LEVEL or captured by an observability backend.
_DIVIDER = "=" * 50


async def interactive_session():
    """Interactive CLI session with persistent agents and memory"""

    print("Welcome to FastOMOP - the OMOP Clinical Query Workflow")
    print(_DIVIDER)
    logger.info("Initializing agents (this may take a moment)...")

    # Generate session and user IDs for memory persistence
    session_id = str(uuid4())
    user_id = "default_user"

    try:
        # Initialize workflow once
        from agno_fastomop.workflows.omop_workflow import initialize_workflow

        await initialize_workflow()

        print("Agents initialized! Enter your query or type 'exit' to quit")
        print(f"Session ID: {session_id}")
        print(_DIVIDER)

        while True:
            user_query = input("Enter your query: ")
            if user_query.lower() == "exit":
                logger.info("Shutting down...")
                await cleanup_workflow()
                print("Goodbye!")
                break

            try:
                logger.info("Processing query")
                response = await run_omop_query(user_query, session_id=session_id, user_id=user_id)
                print(_DIVIDER)
                print(response.content)
                print(_DIVIDER)

            except Exception:
                logger.exception("Query failed")
                print("Please try again")

    except Exception:
        logger.exception("Failed to initialize")
        await cleanup_workflow()


async def batch_mode(dataset_path, output_path=None):
    """Batch mode for processing multiple queries from a file

    Args:
        dataset_path: Path to the file containing queries
        output_path: Path to the file to save the results
    """

    input_file = Path(dataset_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    if output_path is None:
        output_path = input_file.parent / f"{input_file.stem}_results.json"

    print("FastOMOP - Batch Mode")
    print(_DIVIDER)
    logger.info("Processing %s and saving results to %s", input_file, output_path)

    try:
        with open(input_file, "r") as f:
            dataset = json.load(f)

        if isinstance(dataset, list):
            queries = dataset
        elif isinstance(dataset, dict) and "queries" in dataset:
            queries = dataset["queries"]
        elif isinstance(dataset, dict) and "text" in dataset:
            queries = dataset["text"]
        else:
            raise ValueError("Input file must contain a list of queries")

        logger.info("Found %d queries in the dataset", len(queries))

    except json.JSONDecodeError:
        logger.exception("Error parsing JSON in %s", input_file)
        sys.exit(1)

    except Exception:
        logger.exception("Error processing queries from %s", input_file)
        sys.exit(1)

    logger.info("Processing queries...")
    start_time = datetime.now()

    # Each batch gets its own session (queries within batch share context)
    session_id = str(uuid4())
    user_id = "batch_user"
    logger.info("Batch Session ID: %s", session_id)

    results = []
    for i, query_item in enumerate(queries, 1):
        if isinstance(query_item, str):
            query_text = query_item
            query_metadata = {}
        elif isinstance(query_item, dict):
            query_text = (
                query_item.get("query")
                or query_item.get("question")
                or query_item.get("text")
                or query_item.get("input")
            )
            query_metadata = {k: v for k, v in query_item.items() if k not in ["query", "question", "text", "input"]}
        else:
            raise ValueError(f"Invalid query item: {query_item}")

        if not query_text:
            logger.warning("Skipping empty query %d", i)
            continue

        preview = query_text[:80] + ("..." if len(query_text) > 80 else "")
        logger.info("[%d/%d] Processing: %s", i, len(queries), preview)

        result_entry = {
            "query_id": i,
            "query": query_text,
            "metadata": query_metadata,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            query_start = datetime.now()
            result = await run_omop_query(query_text, session_id=session_id, user_id=user_id, batch_mode=True)
            query_end = datetime.now()

            result_entry.update(
                {
                    "status": "success",
                    "response": result.content,
                    "execution_time": (query_end - query_start).total_seconds(),
                }
            )
            logger.info("Query %d completed in %.2fs", i, result_entry["execution_time"])
        except Exception as e:
            logger.exception("Query %d failed", i)
            result_entry.update(
                {
                    "status": "error",
                    "error": str(e),
                    "execution_time": (datetime.now() - query_start).total_seconds(),
                }
            )

        results.append(result_entry)

    # Cleanup workflow after batch
    logger.info("Cleaning up resources...")
    await cleanup_workflow()

    end_time = datetime.now()

    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = len(results) - success_count
    avg_time = sum(r["execution_time"] for r in results) / len(results) if results else 0

    output_doc = {
        "metadata": {
            "input_file": str(input_file),
            "output_file": str(output_path),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "total_time": (end_time - start_time).total_seconds(),
            "total_queries": len(results),
            "successful_queries": success_count,
            "failed_queries": error_count,
            "average_execution_time": avg_time,
        },
        "results": results,
    }

    try:
        with open(output_path, "w") as f:
            json.dump(output_doc, f, indent=2)
        logger.info("Results saved to %s", output_path)
    except OSError:
        logger.exception("Error saving results to %s", output_path)

    print(_DIVIDER)
    print("Batch mode completed")
    print(_DIVIDER)

    return True
