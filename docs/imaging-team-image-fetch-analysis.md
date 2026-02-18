# Incorporating Image-Fetch into the Clinical Imaging Team

## Goal

Make the **Clinical Imaging Team** (semantic → database → imaging) fetch images from HPC using `local_path` from the DB step and pass them to the imaging agent—without replacing the team with a separate workflow.

## How the team currently works

- The team has a single built-in tool: **`delegate_task_to_member(member_id, task)`**.
- When the model calls it, the framework runs `member_agent.run(..., images=images, ...)` where **`images`** comes from:
  1. The **initial run input** (`run_input.images`), and
  2. Any **context images** from `get_team_run_context_images(team_run_context)` (previous members’ response images, if any).
- So the imaging agent only sees images that were in the user’s initial message or that were returned by a previous member. The DB agent returns **text** (e.g. CSV with `local_path`), not images, so today the imaging agent never receives fetched pixel data.

## Options analysed

### Option 1: Custom tool on the team (recommended)

**Idea:** Add a second tool, e.g. **`delegate_to_imaging_with_images(task, db_results)`**, that:

1. Takes the DB agent’s text output as `db_results`.
2. Parses `local_path` from it (reuse `parse_local_paths_from_db_content`).
3. Fetches images via `fetch_hpc_image(remote_path)` for each path (capped).
4. Calls the imaging agent with `imaging_agent.run(task=task, images=fetched_images)` and returns the agent’s response (e.g. `content`).

**Implementation:**

- Create an Agno **`Function`** with:
  - `name`: e.g. `delegate_to_imaging_with_images`
  - `description`: instruct the model to use this when delegating to the Clinical Imaging Agent so images are fetched from HPC.
  - `parameters`: `task` (str), `db_results` (str) — DB agent output.
  - `entrypoint`: callable that closes over the **imaging agent** and does parse → fetch → run → return.
- Register this function in the team: **`Team(..., tools=[..., delegate_to_imaging_with_images_tool])`**.
- Update **team instructions**: when delegating to the Clinical Imaging Agent, use **`delegate_to_imaging_with_images(task=..., db_results=...)`** and pass the full DB agent output as `db_results`; do **not** use `delegate_task_to_member` for the imaging agent.

**Pros:**

- No new workflow; everything stays in the “Clinical Imaging Team”.
- No Team subclass; compatible with Agno upgrades.
- Small, localized change (one tool + instructions).

**Cons:**

- Relies on the model following instructions (use the imaging tool and pass `db_results`). Can be reinforced with clear instructions and, if needed, examples.

---

### Option 2: Custom Team subclass (intercept delegation)

**Idea:** Subclass **`Team`** and override the logic that runs a member so that when the delegate target is the **imaging agent**:

1. Read the last member response (DB agent) from `team_run_context` (e.g. `member_responses`).
2. Parse that content for `local_path`.
3. Fetch images via `fetch_hpc_image`.
4. Call `member_agent.run(..., images=fetched_images)` instead of using only `run_input.images`.

**Implementation:**

- Override **`_get_delegate_task_function`** (or the inner closure that calls `member_agent.run`) so that when `member_agent` is the imaging agent, `images` is replaced or extended with the fetched list before calling `run`.
- Use **`_find_member_by_id`** / agent id or name to detect the imaging agent.

**Pros:**

- Transparent to the model: it keeps using **`delegate_task_to_member(member_id, task)`**; images are injected automatically.

**Cons:**

- **`_get_delegate_task_function`** is large and stateful; overriding it is brittle and may break on Agno updates.
- Requires maintaining a custom Team subclass.

---

### Option 3: Inject images into `team_run_context`

**Idea:** The team already extends `images` with **`get_team_run_context_images(team_run_context)`**. If we could put fetched images into `team_run_context` after the DB step, the next delegation would see them.

**Problem:**

- The DB agent does not produce images; we must run our own “fetch” step (parse + `fetch_hpc_image`).
- That step has to run **after** the DB agent and **before** the imaging agent. The only way to do that inside the team is either:
  - A **tool** that runs after DB and “stores” images somewhere the delegate logic reads (e.g. `session_state["pending_imaging_images"]`), and then the **delegate** path must be changed to use that when the target is the imaging agent (so we still need custom delegate logic), or
  - A **hook/callback** when a member finishes (if Agno exposed one), which it doesn’t in a generic way.

So this option either reduces to “custom tool + custom delegate behaviour” or “subclass”, and doesn’t simplify the design.

---

## Recommendation

- **Use Option 1 (custom tool)** to incorporate image-fetch into the Clinical Imaging Team: add **`delegate_to_imaging_with_images(task, db_results)`** and instruct the team to use it for the imaging agent.
- Keep the existing **Clinical Imaging Pipeline** workflow as an alternative path that guarantees the order semantic → database → image-fetch → imaging with no reliance on the model choosing the right tool.

Implementing Option 1 next in the codebase.
