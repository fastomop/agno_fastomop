"""
Clinical Imaging Pipeline Workflow

4-step workflow: Semantic → Database → Image fetch (from HPC) → Imaging agent.
Fetches images from HPC using local_path from the DB step and passes them to the imaging agent.
"""

import csv
import io
from typing import List

from agno.workflow import Workflow, Step
from agno.workflow.types import StepInput, StepOutput
from agno.tools.function import Function

from agno_fastomop.tools.hpc_image import fetch_hpc_image

# Max images to fetch per run (avoid timeouts and token limits)
MAX_IMAGES_TO_FETCH = 5


def parse_local_paths_from_db_content(content: str) -> List[str]:
    """
    Extract local_path values from the database step output.

    Handles CSV-style output (e.g. from OMCP Select_Query), markdown tables,
    and plain text lines that look like absolute paths.

    Returns:
        List of non-empty path strings, deduplicated, up to MAX_IMAGES_TO_FETCH.
    """
    if not content or not content.strip():
        return []

    paths: List[str] = []
    content_stripped = content.strip()

    # 1) Try CSV: header with local_path, then data rows
    if "local_path" in content_stripped.lower():
        try:
            reader = csv.reader(io.StringIO(content_stripped))
            rows = list(reader)
        except Exception:
            rows = []
        if rows:
            header = [c.strip().lower() for c in rows[0]]
            try:
                path_col = header.index("local_path")
            except ValueError:
                path_col = -1
            if path_col >= 0:
                for r in rows[1:]:
                    if path_col < len(r):
                        val = r[path_col].strip()
                        if val and (val.startswith("/") or "." in val):
                            paths.append(val)
        if paths:
            seen = set()
            out = []
            for p in paths:
                if p not in seen and p:
                    seen.add(p)
                    out.append(p)
            return out[:MAX_IMAGES_TO_FETCH]

    # 2) Line-based: lines that look like absolute paths
    for line in content_stripped.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("local_path") or "|" in line and "local_path" in line.lower():
            continue
        # Remove markdown table pipes and split by pipe/table
        if "|" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            for p in parts:
                if p.startswith("/") and ("/" in p[1:] or "." in p):
                    paths.append(p)
                    break
        elif line.startswith("/") and ("/" in line[1:] or "." in line):
            paths.append(line)

    seen = set()
    out = []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out[:MAX_IMAGES_TO_FETCH]


def image_fetch_step(step_input: StepInput) -> StepOutput:
    """
    Workflow step: parse previous (Database) step output for local_path,
    fetch those images from HPC, and return them with the DB content for the next step.
    """
    content = step_input.get_last_step_content()
    if isinstance(content, (dict, list)):
        import json
        content = json.dumps(content, default=str)
    text = (content or "").strip()

    paths = parse_local_paths_from_db_content(text)
    images = []
    errors = []
    for remote_path in paths:
        try:
            img = fetch_hpc_image(remote_path=remote_path)
            images.append(img)
        except Exception as e:
            errors.append(f"{remote_path}: {e}")

    # Keep DB content for the imaging agent; optionally append fetch summary
    out_content = text
    if errors:
        out_content = out_content + "\n\n(Image fetch issues: " + "; ".join(errors[:3]) + ")"
    if images:
        out_content = out_content + f"\n\n(Fetched {len(images)} image(s) from HPC for analysis.)"

    return StepOutput(
        content=out_content,
        images=images if images else None,
        success=True,
    )


def make_delegate_to_imaging_with_images_tool(imaging_agent):
    """
    Build a Team tool that delegates to the Clinical Imaging Agent with images
    fetched from HPC using local_path from the DB agent output.

    Use this tool (instead of delegate_task_to_member) when the team delegates
    to the Clinical Imaging Agent so that images are actually fetched and passed.
    """

    def delegate_to_imaging_with_images(task: str, db_results: str) -> str:
        """Fetch images from HPC using db_results (DB agent output) and run imaging agent with them."""
        paths = parse_local_paths_from_db_content(db_results or "")
        images = []
        errors = []
        for remote_path in paths:
            try:
                img = fetch_hpc_image(remote_path=remote_path)
                images.append(img)
            except Exception as e:
                errors.append(f"{remote_path}: {e}")
        # Run imaging agent with task and fetched images
        response = imaging_agent.run(
            input=task,
            images=images if images else None,
        )
        content = (response.content or "").strip()
        if errors and content:
            content += "\n\n(Note: some images could not be fetched: " + "; ".join(errors[:3]) + ")"
        return content

    return Function(
        name="delegate_to_imaging_with_images",
        description=(
            "Delegate to the Clinical Imaging Agent with images fetched from HPC. "
            "Use this (instead of delegate_task_to_member) when delegating to the Clinical Imaging Agent: "
            "pass the full Database agent output as db_results so images can be fetched from local_path and analyzed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Clear description of the task for the Clinical Imaging Agent (include user question and what to analyze).",
                },
                "db_results": {
                    "type": "string",
                    "description": "Full text output from the OMOP Database Agent (must include image_occurrence/local_path data).",
                },
            },
            "required": ["task", "db_results"],
        },
        entrypoint=delegate_to_imaging_with_images,
    )


def initialize_clinical_imaging_pipeline(semantic_agent, database_agent, imaging_agent) -> Workflow:
    """
    Build the 4-step Clinical Imaging Pipeline workflow.

    Steps: Semantic → Database → Image fetch (from HPC) → Imaging agent.
    The image-fetch step parses the DB output for local_path and passes fetched
    images to the imaging agent.

    Args:
        semantic_agent: OMOP Semantic Agent (from OMOP workflow).
        database_agent: OMOP Database Agent (from OMOP workflow).
        imaging_agent: Clinical Imaging Agent (from imaging workflow).

    Returns:
        Workflow configured for AgentOS.
    """
    from agno.db.sqlite import SqliteDb

    db = SqliteDb(db_file="db_agent.db")

    return Workflow(
        name="Clinical Imaging Pipeline",
        db=db,
        debug_mode=True,
        steps=[
            Step(
                name="Semantic Extraction",
                agent=semantic_agent,
                description="Extract clinical concepts and classify imaging query",
                add_workflow_history=False,
                num_history_runs=0,
            ),
            Step(
                name="SQL Generation and Execution",
                agent=database_agent,
                description="Query image_occurrence, image_feature, note and get local_path",
                add_workflow_history=False,
                num_history_runs=0,
            ),
            Step(
                name="Image Fetch",
                executor=image_fetch_step,
                description="Fetch images from HPC using local_path from DB results",
            ),
            Step(
                name="Image Analysis",
                agent=imaging_agent,
                description="Analyze fetched images with metadata and reports",
                add_workflow_history=False,
                num_history_runs=0,
            ),
        ],
    )
