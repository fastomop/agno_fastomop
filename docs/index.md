# FastOMOP

Natural language interface for OMOP CDM clinical databases using multi-agent workflows.

## Quick start

See the [README](https://github.com/fastomop/agno_fastomop#installation) for the
full installation, configuration, and usage flow.

## Architecture overview

FastOMOP translates natural-language clinical queries into OMOP CDM-compliant
SQL through a two-stage pipeline:

1. **Semantic agent** — maps clinical terms to OMOP concepts and captures
   query intent as a `SemanticContext` JSON payload.
2. **Database agent** — generates and executes OMOP CDM SQL, grounded on the
   system prompt and the live schema returned by the OMCP MCP server.

All executions can be traced to Langfuse for evaluation and prompt
optimisation when `LANGFUSE_ENABLED=true`.

## Documentation

This documentation site is built with [zensical](https://zensical.org/) and
deployed automatically on pushes to `main`. To preview locally:

```bash
uv sync --extra docs
uv run zensical serve
```
