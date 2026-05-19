"""Unit tests for `agno_fastomop.config` — pure-Python, no external services."""

import pytest

from agno_fastomop.config import deep_merge, validate_config


class TestDeepMerge:
    def test_overrides_top_level_scalars(self):
        assert deep_merge({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}

    def test_recursively_merges_nested_dicts(self):
        base = {"models": {"providers": {"openai": {"id": "gpt-4"}}}}
        override = {"models": {"providers": {"openai": {"id": "gpt-4-turbo"}}}}
        result = deep_merge(base, override)
        assert result["models"]["providers"]["openai"]["id"] == "gpt-4-turbo"

    def test_keeps_unrelated_nested_keys(self):
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 3}}
        assert deep_merge(base, override) == {"a": {"x": 1, "y": 3}}

    def test_does_not_mutate_base(self):
        base = {"a": 1, "nested": {"b": 2}}
        deep_merge(base, {"a": 99, "nested": {"b": 99}})
        assert base == {"a": 1, "nested": {"b": 2}}

    def test_override_replaces_scalar_with_dict(self):
        # When override's value is a dict but base's is a scalar, override wins.
        assert deep_merge({"a": 1}, {"a": {"x": 1}}) == {"a": {"x": 1}}


class TestValidateConfig:
    """`validate_config` reads providers from the default `config.toml` (ollama)
    and the optional `LANGFUSE_ENABLED` toggle from the environment.
    """

    def test_passes_with_ollama_host_and_langfuse_disabled(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        validate_config()  # must not raise

    def test_treats_missing_langfuse_enabled_as_false(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
        monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        validate_config()  # must not raise

    def test_raises_when_langfuse_enabled_without_keys(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        with pytest.raises(ValueError, match="LANGFUSE"):
            validate_config()

    def test_raises_when_ollama_host_missing(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        with pytest.raises(ValueError, match="OLLAMA_HOST"):
            validate_config()
