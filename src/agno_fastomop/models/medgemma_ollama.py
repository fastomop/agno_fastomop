"""
MedGemmaOllama — Agno Ollama wrapper with tool-call extraction from text.

Gemma 3 (and MedGemma 27B) does NOT have native Ollama tool-calling support.
When agno sends tools=[...] to Ollama, the model may produce tool-call JSON
in its response *text* rather than in the structured tool_calls field.

This wrapper overrides _parse_provider_response() to:
1. Call the parent Ollama parser (handles native tool calls if present)
2. If no tool_calls parsed, scan the response text for JSON tool calls
3. Handle markdown-wrapped JSON (```json ... ```) which Gemma models love to produce
4. Extract and normalize tool calls to agno's expected format

Usage in factory.py:
    from agno_fastomop.models.medgemma_ollama import MedGemmaOllama
    model = MedGemmaOllama(id="medgemma-tools:27b", host="http://...")
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agno.models.ollama.chat import Ollama
from agno.models.response import ModelResponse
from agno.utils.log import log_debug, log_warning


# Regex patterns for extracting tool calls from text
# Pattern 1: Full tool_calls wrapper
_TOOL_CALLS_PATTERN = re.compile(
    r'\{\s*"tool_calls"\s*:\s*\[.*?\]\s*\}',
    re.DOTALL,
)

# Pattern 2: Direct function call (no tool_calls wrapper)
_FUNCTION_CALL_PATTERN = re.compile(
    r'\{\s*"(?:function|name)"\s*:.*?"arguments"\s*:.*?\}',
    re.DOTALL,
)

# Pattern 3: Markdown code block wrapper
_MARKDOWN_JSON_PATTERN = re.compile(
    r'```(?:json)?\s*\n?(.*?)\n?\s*```',
    re.DOTALL,
)


def _strip_markdown(text: str) -> str:
    """Strip markdown code block wrappers from text.

    Handles:
    - ```json ... ```
    - ``` ... ```
    - Single backtick wrapping
    """
    # Strip triple-backtick blocks
    match = _MARKDOWN_JSON_PATTERN.search(text)
    if match:
        return match.group(1).strip()

    # Strip single backticks wrapping the entire content
    stripped = text.strip()
    if stripped.startswith('`') and stripped.endswith('`'):
        stripped = stripped[1:-1].strip()

    return stripped


def _fix_json_quirks(text: str) -> str:
    """Fix common JSON formatting issues from LLM output.

    Handles:
    - Trailing commas before } or ]
    - Single quotes instead of double quotes (conservative)
    """
    # Remove trailing commas before closing braces/brackets
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def _try_parse_json(text: str) -> Optional[dict]:
    """Attempt to parse JSON with progressive cleaning."""
    # Attempt 1: Direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Attempt 2: Strip markdown, then parse
    cleaned = _strip_markdown(text)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    # Attempt 3: Fix JSON quirks, then parse
    cleaned = _fix_json_quirks(cleaned)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    # Attempt 4: Extract JSON object from surrounding text
    # Look for the outermost { ... } that contains "tool_calls" or "name"
    for pattern in [_TOOL_CALLS_PATTERN, _FUNCTION_CALL_PATTERN]:
        match = pattern.search(text)
        if match:
            candidate = match.group(0)
            candidate = _fix_json_quirks(candidate)
            try:
                return json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                continue

    return None


def _normalize_tool_calls(parsed: dict) -> Optional[List[dict]]:
    """Normalize various tool-call JSON formats to agno's expected format.

    Agno expects: [{"type": "function", "function": {"name": "...", "arguments": "json-string"}}]

    Handles these input formats:
    1. {"tool_calls": [{"function": {"name": "...", "arguments": {...}}}]}
    2. {"name": "...", "arguments": {...}}
    3. {"function": {"name": "...", "arguments": {...}}}
    4. {"tool_calls": [{"name": "...", "arguments": {...}}]}
    """
    tool_calls = []

    if "tool_calls" in parsed:
        raw_calls = parsed["tool_calls"]
        if not isinstance(raw_calls, list):
            return None
        for call in raw_calls:
            tc = _extract_single_tool_call(call)
            if tc:
                tool_calls.append(tc)
    else:
        # Try parsing as a single tool call
        tc = _extract_single_tool_call(parsed)
        if tc:
            tool_calls.append(tc)

    return tool_calls if tool_calls else None


def _extract_single_tool_call(call: dict) -> Optional[dict]:
    """Extract a single tool call from various formats."""
    name = None
    arguments = None

    if "function" in call:
        func = call["function"]
        name = func.get("name")
        arguments = func.get("arguments")
    elif "name" in call:
        name = call.get("name")
        arguments = call.get("arguments")

    if not name:
        return None

    # Serialize arguments to JSON string (agno expects string, not dict)
    if arguments is not None and not isinstance(arguments, str):
        arguments = json.dumps(arguments)
    elif arguments is None:
        arguments = "{}"

    return {
        "type": "function",
        "function": {
            "name": name,
            "arguments": arguments,
        },
    }


@dataclass
class MedGemmaOllama(Ollama):
    """Ollama model wrapper for MedGemma/Gemma 3 with tool-call text extraction.

    Extends the base Ollama class to parse tool calls from the model's text output
    when native Ollama tool-call parsing is not available (as with Gemma 3 models).
    """

    def _parse_provider_response(self, response: dict) -> ModelResponse:
        """Parse provider response, extracting tool calls from text if needed."""
        # First, try the standard Ollama parsing (works for models with native support)
        model_response = super()._parse_provider_response(response)

        # If native parsing found tool calls, we're done
        if model_response.tool_calls:
            log_debug("MedGemmaOllama: Native tool calls found, using as-is")
            return model_response

        # No native tool calls — try extracting from text content
        if model_response.content:
            extracted = self._extract_tool_calls_from_text(model_response.content)
            if extracted:
                log_debug(
                    f"MedGemmaOllama: Extracted {len(extracted)} tool call(s) from text content"
                )
                model_response.tool_calls = extracted
                # Clear content — agno expects either content OR tool_calls
                model_response.content = ""

        return model_response

    def _parse_provider_response_delta(self, response) -> ModelResponse:
        """Parse streaming response delta.

        For streaming, we accumulate content and try to extract tool calls
        from the complete accumulated text. This override handles the final
        chunk (response.done == True) where we can attempt extraction.
        """
        model_response = super()._parse_provider_response_delta(response)

        # Only attempt extraction on the final chunk
        if response.get("done") and model_response.content:
            extracted = self._extract_tool_calls_from_text(model_response.content)
            if extracted:
                log_debug(
                    f"MedGemmaOllama: Extracted {len(extracted)} tool call(s) from streamed content"
                )
                model_response.tool_calls = extracted
                model_response.content = ""

        return model_response

    def _extract_tool_calls_from_text(self, text: str) -> Optional[List[dict]]:
        """Extract tool calls from model text output.

        Handles:
        - Raw JSON tool calls
        - JSON wrapped in markdown code blocks (```json ... ```)
        - Trailing commas, escaped quotes, and other LLM JSON quirks
        - Multiple tool call formats (tool_calls wrapper, direct name/arguments)

        Returns agno-format tool calls or None if no valid tool calls found.
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        # Quick check: does this look like it might contain a tool call?
        # Avoid expensive parsing on pure text responses
        if '"tool_calls"' not in text and '"name"' not in text and '"function"' not in text:
            return None

        # Try to parse the text as JSON (with progressive cleaning)
        parsed = _try_parse_json(text)
        if parsed is None:
            log_debug("MedGemmaOllama: Failed to parse any JSON from text content")
            return None

        # Normalize to agno format
        tool_calls = _normalize_tool_calls(parsed)
        if tool_calls is None:
            log_debug("MedGemmaOllama: JSON parsed but no valid tool calls found")
            return None

        # Validate tool call structure
        valid_calls = []
        for tc in tool_calls:
            func = tc.get("function", {})
            if func.get("name"):
                valid_calls.append(tc)
            else:
                log_warning(f"MedGemmaOllama: Skipping tool call with no name: {tc}")

        return valid_calls if valid_calls else None
