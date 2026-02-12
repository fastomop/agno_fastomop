import asyncio
from agno_fastomop.workflows.omop_workflow import run_omop_query, cleanup_workflow
import argparse
import sys
from pathlib import Path
import json
from datetime import datetime
from uuid import uuid4
from typing import Optional


async def interactive_session():
    """Interactive CLI session with persistent agents and memory"""

    print("Welcome to FastOMOP - the OMOP Clinical Query Workflow")
    print("="*50)
    print("Initializing agents (this may take a moment)...")

    # Generate session and user IDs for memory persistence
    session_id = str(uuid4())
    user_id = "default_user"

    try:
        # Initialize workflow once
        from agno_fastomop.workflows.omop_workflow import initialize_workflow
        await initialize_workflow()

        print("Agents initialized! Enter your query or type 'exit' to quit")
        print(f"Session ID: {session_id}")
        print("="*50)

        while True:
            user_query = input("Enter your query: ")
            if user_query.lower() == "exit":
                print("Shutting down...")
                await cleanup_workflow()
                print("Goodbye!")
                break

            try:
                print("Processing...")
                response = await run_omop_query(user_query, session_id=session_id, user_id=user_id)
                print("="*50)
                print(response.content)
                print("="*50)

            except Exception as e:
                print(f"Error: {e}")
                print("Please try again")

    except Exception as e:
        print(f"Failed to initialize: {e}")
        await cleanup_workflow()


async def batch_mode(dataset_path, output_path=None):
    """Batch mode for processing multiple queries from a file
    
    Args:
        dataset_path: Path to the file containing queries
        output_path: Path to the file to save the results
    """
    
    input_file =Path(dataset_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    if output_path is None:
        output_path = input_file.parent / f"{input_file.stem}_results.json"
    
    print("FastOMOP - Batch Mode")
    print("="*50)
    print(f"Processing {input_file} and saving results to {output_path}")
    print("="*50)

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

        print(f"Found {len(queries)} queries in the dataset")
        print("="*50)

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        print("Please check the input file format")
        sys.exit(1)

    except Exception as e:
        print(f"Error processing queries: {e}")
        print("Please try again")
        sys.exit(1)

    print("Processing queries...")
    print("="*50)
    start_time = datetime.now()

    # Each batch gets its own session (queries within batch share context)
    session_id = str(uuid4())
    user_id = "batch_user"
    print(f"Batch Session ID: {session_id}")

    results = []
    for i, query_item in enumerate(queries, 1):

        if isinstance(query_item, str):
            query_text = query_item
            query_metadata = {}
        elif isinstance(query_item, dict):
            query_text = query_item.get("query") or query_item.get("question") or query_item.get("text") or query_item.get("input")
            query_metadata = {k: v for k, v in query_item.items() if k not in ['query', 'question', 'text', 'input']}
        else:
            raise ValueError(f"Invalid query item: {query_item}")

        if not query_text:
            print(f"Skipping empty query {i}")
            continue

        print(f"\n[{i}/{len(queries)}] Processing: {query_text[:80]}{'...' if len(query_text) > 80 else ''}")

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

            result_entry.update({
                "status": "success",
                "response": result.content,
                "execution_time": (query_end - query_start).total_seconds(),
            })
            print(f"Query {i} completed in {result_entry['execution_time']:.2f} seconds")
        except Exception as e:
            result_entry.update({
                "status": "error",
                "error": str(e),
                "execution_time": (datetime.now() - query_start).total_seconds(),
            })

        results.append(result_entry)

    # Cleanup workflow after batch
    print("Cleaning up resources...")
    await cleanup_workflow()

    end_time = datetime.now()

    success_count = sum(1 for r in results if r['status'] == 'success')
    error_count = len(results) - success_count
    avg_time = sum(r['execution_time'] for r in results) / len(results) if results else 0

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
        print(f"Results saved to {output_path}")
    except Exception as e:
        print(f"Error saving results: {e}")
        print("Please try again")

    print("="*50)
    print("Batch mode completed")
    print("="*50)

    return True


async def imaging_session():
    """Interactive CLI session for the imaging agent"""
    from agno_fastomop.workflows.imaging_workflow import (
        run_imaging_query,
        run_imaging_query_local,
        cleanup_imaging_workflow,
    )

    print("Welcome to FastOMOP - Clinical Imaging Analysis")
    print("=" * 50)
    print("Modes:")
    print("  Remote: Fetch image from HPC node via SSH")
    print("  Local:  Analyze a local image file")
    print("=" * 50)

    session_id = str(uuid4())
    user_id = "default_user"
    print(f"Session ID: {session_id}")

    try:
        while True:
            print("\nOptions:")
            print("  [r] Analyze remote HPC image")
            print("  [l] Analyze local image")
            print("  [exit] Quit")
            choice = input("Choice: ").strip().lower()

            if choice == "exit":
                print("Shutting down...")
                await cleanup_imaging_workflow()
                print("Goodbye!")
                break

            if choice == "r":
                remote_path = input("Remote image path (on HPC): ").strip()
                if not remote_path:
                    print("Path cannot be empty")
                    continue

                message = input("Your question about the image: ").strip()
                if not message:
                    message = "Analyze this image and describe your findings."

                metadata_str = input("Metadata JSON (optional, press Enter to skip): ").strip()
                metadata = None
                if metadata_str:
                    try:
                        metadata = json.loads(metadata_str)
                    except json.JSONDecodeError:
                        print("Warning: Invalid JSON, proceeding without metadata")

                try:
                    print("Fetching image and running analysis...")
                    response = await run_imaging_query(
                        remote_path=remote_path,
                        message=message,
                        metadata=metadata,
                        session_id=session_id,
                        user_id=user_id,
                    )
                    print("=" * 50)
                    print(response.content)
                    print("=" * 50)
                except Exception as e:
                    print(f"Error: {e}")

            elif choice == "l":
                local_path = input("Local image path: ").strip()
                if not local_path or not Path(local_path).exists():
                    print(f"File not found: {local_path}")
                    continue

                message = input("Your question about the image: ").strip()
                if not message:
                    message = "Analyze this image and describe your findings."

                metadata_str = input("Metadata JSON (optional, press Enter to skip): ").strip()
                metadata = None
                if metadata_str:
                    try:
                        metadata = json.loads(metadata_str)
                    except json.JSONDecodeError:
                        print("Warning: Invalid JSON, proceeding without metadata")

                try:
                    print("Running analysis...")
                    response = await run_imaging_query_local(
                        image_path=local_path,
                        message=message,
                        metadata=metadata,
                        session_id=session_id,
                        user_id=user_id,
                    )
                    print("=" * 50)
                    print(response.content)
                    print("=" * 50)
                except Exception as e:
                    print(f"Error: {e}")

            else:
                print("Unknown option. Use 'r', 'l', or 'exit'.")

    except Exception as e:
        print(f"Failed: {e}")
        await cleanup_imaging_workflow()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FastOMOP - OMOP Clinical Query Workflow")
    parser.add_argument("--batch", type=str, help="Path to the dataset file")
    parser.add_argument("--output", type=str, help="Path to the output file")
    parser.add_argument("--imaging", action="store_true", help="Run imaging analysis mode")
    args = parser.parse_args()

    if args.imaging:
        asyncio.run(imaging_session())
    elif args.batch:
        asyncio.run(batch_mode(args.batch, args.output))
    else:
        asyncio.run(interactive_session())