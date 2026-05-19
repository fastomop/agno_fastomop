# FastOMOP

Natural language interface for OMOP CDM clinical databases using multi-agent workflows.

## Overview

FastOMOP translates natural language clinical queries into OMOP CDM-compliant SQL queries through a two-stage pipeline:

1. **Semantic Agent**: Maps clinical terms to OMOP concepts and evaluates query intent
2. **Database Agent**: Generates and executes OMOP CDM queries with knowledge-augmented retrieval

All executions are traced to Langfuse for evaluation and prompt optimization.

## Requirements

- Python 3.13+
- UV package manager
- OMOP CDM database
- LLM provider (one of: Azure OpenAI, OpenAI, Anthropic, or Ollama)
- Langfuse account (optional — enable with `LANGFUSE_ENABLED=true`)

### Logging

FastOMOP uses Python's standard `logging` module. Set the verbosity via the
`LOG_LEVEL` env var (`DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL`,
default `INFO`):

```bash
LOG_LEVEL=DEBUG uv run python -m agno_fastomop.run_agent
```

Interactive CLI banners (welcome / prompt / goodbye) still go to stdout via
`print()` — they are part of the REPL UI, not diagnostic output.

## Installation

```bash
# Clone repository
git clone <repository-url>
cd agno_fastomop

# Install dependencies with UV
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials
```

## Configuration

### Environment Variables

Create a `.env` file with the following required variables:

```bash
# OMOP Database (required)
DB_PATH=/path/to/omop.duckdb # or see OMCP docs for postgresql/general db set-up

# OMCP server checkout (required — used to launch the MCP server)
OMCP_SERVER_DIR=/path/to/omcp_server

# Langfuse (optional — only enforced when LANGFUSE_ENABLED=true)
LANGFUSE_ENABLED=false
# LANGFUSE_PUBLIC_KEY=pk-lf-...
# LANGFUSE_SECRET_KEY=sk-lf-...
# LANGFUSE_HOST=https://cloud.langfuse.com
```

Add credentials for your chosen LLM provider:

**Azure OpenAI:**
```bash
AZURE_OPENAI_API_KEY=your_api_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your_deployment_name
```

**OpenAI:**
```bash
OPENAI_API_KEY=sk-...
```

**Anthropic:**
```bash
ANTHROPIC_API_KEY=sk-ant-...
```

**Ollama:**
```bash
OLLAMA_HOST=http://localhost:11434
```

### Model Configuration

Edit `config.toml` to configure model providers and agent settings.

**Azure OpenAI:**
```toml
[models]
default_provider = "azure"

[models.providers.azure]
provider = "azure"
model_id = "gpt-4.1"
api_version = "2025-01-01-preview"

[agents.database]
model_provider = "azure"

[agents.semantic]
model_provider = "azure"
```

**OpenAI:**
```toml
[models]
default_provider = "openai"

[models.providers.openai]
provider = "openai"
model_id = "gpt-4-turbo-preview"

[agents.database]
model_provider = "openai"

[agents.semantic]
model_provider = "openai"
```

**Anthropic:**
```toml
[models]
default_provider = "anthropic"

[models.providers.anthropic]
provider = "anthropic"
model_id = "claude-3-5-sonnet-20241022"

[agents.database]
model_provider = "anthropic"

[agents.semantic]
model_provider = "anthropic"
```

**Ollama:**
```toml
[models]
default_provider = "ollama"

[models.providers.ollama]
provider = "ollama"
model_id = "qwen2.5:7b"

[agents.database]
model_provider = "ollama"

[agents.semantic]
model_provider = "ollama"
```

**Mixed Providers (cost optimization):**
```toml
[models]
default_provider = "azure"

[agents.database]
model_provider = "azure"  # Use Azure GPT-4 for complex SQL generation

[agents.semantic]
model_provider = "ollama"  # Use local model for concept mapping
```

### MCP Server Configuration

The OMOP MCP server command is templated in `config.toml` and resolves
`${OMCP_SERVER_DIR}` from your `.env` at load time:

```toml
[omcp]
transport = "stdio"
command = "uv run --directory ${OMCP_SERVER_DIR} python src/omcp/main.py"
```

Set `OMCP_SERVER_DIR` in `.env` to the path of your `omcp_server` checkout,
or override the whole command via the `MCP_COMMAND` env var.

## Bootstrap

Upload agent prompts to Langfuse before first use (only required when
`LANGFUSE_ENABLED=true`; otherwise the agents fall back to the local
prompt files under `src/agno_fastomop/prompts/`):

```bash
uv run python -m agno_fastomop.bootstrap
```

## Usage

### Interactive Mode

```bash
uv run python -m agno_fastomop.run_agent
```

Enter queries at the prompt:

```
Enter your query: Patients taking metformin
Processing...
==================================================
The query found 127 patients taking metformin.
==================================================
```

Type `exit` to quit.

### Batch Processing

Create a JSON file with queries:

```json
[
  "Patients taking amlodipine 2.5 MG Oral Tablet",
  "Distribution of patients by birth year",
  "Patients with diabetes and hypertension within 90 days"
]
```

Run batch processing:

```bash
uv run python -m agno_fastomop.run_agent --batch queries.json
```

Results are saved to `queries_results.json` with the following structure:

```json
{
  "metadata": {
    "total_queries": 10,
    "successful_queries": 9,
    "failed_queries": 1,
    "average_execution_time": 25.3
  },
  "results": [
    {
      "query_id": 1,
      "query": "Patients taking metformin",
      "status": "success",
      "response": "The query found 127 patients taking metformin.",
      "execution_time": 22.1
    }
  ]
}
```

### Supported Input Formats

Batch mode accepts multiple JSON formats:

**Simple list:**
```json
["query 1", "query 2"]
```

**With metadata:**
```json
[
  {
    "query": "Patients with diabetes",
    "category": "condition",
    "expected_count": 100
  }
]
```

**Dictionary format:**
```json
{
  "queries": ["query 1", "query 2"]
}
```

### Web Interface

Launch the web-based interface powered by AgentOS:

```bash
uv run python -m agno_fastomop.web_interface
```

The backend runs at `http://localhost:7777` and exposes the API (workflows, agents). To use the **web UI** (chat, workflow execution, monitoring), you must connect it via the **AgentOS Control Plane**:

1. With the backend running, open [os.agno.com](https://os.agno.com) and sign in
2. Click **"Add new OS"**
3. Add your instance:
   - **Endpoint URL**: `http://localhost:7777` (or `http://<your-ip>:7777` for network access)
   - **OS Name**: e.g. "FastOMOP" or "Development"
4. Use the Control Plane to chat with agents, run workflows, and view traces.

The Control Plane connects directly from your browser to your AgentOS runtime. Auto-reload is disabled on the backend to prevent DuckDB file locking conflicts.

## Architecture

### Workflow Pattern (Current)

```
User Query → Semantic Agent → Database Agent → Response
```

1. **Semantic Agent**: Queries OMOP concept table to map terms to standard concepts
2. **Database Agent**: Generates SQL using retrieved concepts and OMOP world model knowledge

### Observability

All workflow executions are traced to Langfuse via the `@observe()` decorator:

- Full execution traces with timing
- Agent interactions and tool calls
- LLM prompts and completions
- MCP tool execution results

Access traces at your Langfuse dashboard for evaluation and debugging.

### Grounding

The database agent grounds its SQL generation on the system prompt
(`prompts/database_agent.txt`) and the live schema returned by the
OMCP MCP server. There is no separate vector knowledge base.

### Prompt Management

Agent prompts are stored in Langfuse and loaded dynamically:

- `semantic_agent`: Concept mapping instructions
- `database_agent`: SQL generation guidelines
- `supervisor`: Orchestration logic (alternative pattern)

Prompts can be versioned and A/B tested through Langfuse.

## Development

### Tooling

The repository uses the Astral stack:

- **uv** for package management and builds (`uv sync`, `uv build`).
- **Ruff** for linting and formatting (`uv run ruff check`, `uv run ruff format`).
- **prek** as a drop-in modern replacement for pre-commit (`uvx prek install`, `uvx prek run --all-files`).
- **ty** for type checking (alpha; advisory only — `uv run ty check src`).
- **zensical** for the documentation site (`uv sync --extra docs && uv run zensical serve`).

Install everything in one go:

```bash
uv sync --all-extras
uvx prek install
```

### Project Structure

```
agno_fastomop/
├── src/agno_fastomop/
│   ├── agents/          # Agent definitions
│   │   ├── database.py
│   │   ├── semantic.py
│   │   ├── supervisor.py
│   │   └── factory.py
│   ├── workflows/       # Workflow orchestration
│   │   └── omop_workflow.py
│   ├── schemas/         # Pydantic models
│   │   └── schemas.py
│   ├── prompts/         # Local prompt templates (uploaded to Langfuse)
│   ├── observability/   # Langfuse integration
│   └── bootstrap.py     # Uploads prompts to Langfuse
├── config.toml          # Configuration
└── README.md
```

### Adding New Query Patterns

1. Update the relevant prompt under `src/agno_fastomop/prompts/`
2. Re-run bootstrap to upload to Langfuse
3. Test with sample queries
4. Monitor execution in Langfuse

### Updating Prompts

1. Edit local prompt files in `src/agno_fastomop/prompts/`
2. Run bootstrap to upload to Langfuse
3. Agents will use new prompts on next execution

### Testing

```bash
# Run interactive mode with test queries
uv run python -m agno_fastomop.run_agent

# Run batch mode with evaluation dataset
uv run python -m agno_fastomop.run_agent --batch test_queries.json
```

## Validation

Verify configuration:

```bash
uv run python -c "from agno_fastomop.config import validate_config; validate_config(); print('Configuration valid')"
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Citation



## Contact

k24118093@kcl.ac.uk
