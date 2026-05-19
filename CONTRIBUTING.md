# Contributing

Thanks for working on FastOMOP. This guide covers the local dev loop and the
conventions CI enforces.

## Setup

Python 3.13 and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --all-extras
uvx prek install
```

`uvx prek install` wires the pre-commit hooks declared in `prek.toml` into
your git config — they run ruff-check, ruff-format, and the basic
file-hygiene checks on every commit.

## Running tests

By default, only unit tests run — integration tests need a live OMCP server,
an OMOP database, and LLM credentials, so they're skipped in CI and in the
default local invocation:

```bash
# Unit tests only (the CI default).
uv run pytest

# Run a specific test file.
uv run pytest tests/unit/test_config.py -v

# Include integration tests (requires .env populated with DB_PATH,
# OMCP_SERVER_DIR, LLM provider keys; LANGFUSE_ENABLED optional).
uv run pytest -m integration

# Run everything.
uv run pytest -m ""
```

Tests that hit external services must be marked with `@pytest.mark.integration`.

## Lint, format, type-check

```bash
uv run ruff check src tests             # lint
uv run ruff format src tests            # format (auto-fix)
uv run ruff format --check src tests    # format (verify only)
uv run ty check src                     # type check (advisory; ty is alpha)
```

`prek run --all-files` runs ruff in the same configuration CI uses.

## Building

```bash
uv build   # produces dist/agno_fastomop-*.tar.gz and *.whl via uv_build
```

## Commit conventions

Use [conventional commit](https://www.conventionalcommits.org/) prefixes:
`fix:`, `feat:`, `chore:`, `refactor:`, `docs:`, `ci:`, `test:`. Keep the
subject under ~70 characters; the body explains the *why*.

## Opening a PR

Stack on top of in-flight PRs when work is sequential — set the new PR's base
to the previous PR's branch (e.g. `--base fix/production-readiness`). GitHub
auto-retargets to `main` once the parent merges.
