from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from inspect import isawaitable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Result type for structured_call
# ---------------------------------------------------------------------------


@dataclass
class StructuredResult:
    """Outcome of a structured_call attempt."""

    success: bool
    data: dict[str, Any] | None = None
    raw: str = ""
    retries: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# High-level: structured_call
# ---------------------------------------------------------------------------


@dataclass
class Example:
    """One input/output example for few-shot prompting."""

    input: str
    output: dict[str, Any]


async def structured_call(
    llm_client: Any,
    config: dict[str, Any],
    tier: str,
    *,
    schema: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    examples: list[Example] | list[dict[str, Any]] | None = None,
    max_retries: int = 1,
    attribution: str | None = None,
    purpose: str | None = None,
) -> StructuredResult:
    """Call an LLM expecting a JSON response, validate, and retry on failure.

    Assembles a prompt from *system_prompt* + schema + examples + *user_prompt*,
    calls the LLM, parses/validates the JSON response against *schema*, and
    retries up to *max_retries* times by appending the validation error.

    Parameters
    ----------
    llm_client : Any
        Injected LLM client with ``complete(messages, config, tier)`` method.
    config : dict
        Provider configuration (provider, api_key, models, etc.).
    tier : str
        Model tier to use (e.g. "commodity", "quality").
    schema : dict
        JSON Schema to validate the response against.
    system_prompt : str
        System-role instructions for the LLM.
    user_prompt : str
        User-role prompt containing the actual task/input.
    examples : list, optional
        Few-shot examples. Each is an ``Example`` dataclass or a dict with
        "input" and "output" keys.
    max_retries : int
        Number of retry attempts on validation failure (default 1).

    Returns
    -------
    StructuredResult
        ``.success`` is True when the response passes validation.
        ``.data`` contains the validated dict, ``.raw`` the raw LLM text.
    """
    normalized_examples = _normalize_examples(examples)
    full_system = _assemble_system_prompt(system_prompt, schema, normalized_examples)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": user_prompt},
    ]

    retries_used = 0
    raw = ""

    for attempt in range(1 + max_retries):
        try:
            raw = await _call_llm(
                llm_client,
                config,
                tier,
                messages,
                attribution=attribution,
                purpose=purpose,
            )
        except Exception as exc:
            # Infrastructure failure (network, API) — don't retry with
            # a fake "assistant" message; fail immediately.
            return StructuredResult(
                success=False,
                data=None,
                raw=raw,
                retries=retries_used,
                error=str(exc),
            )

        try:
            data = parse_json_response(raw)
            validate_json_schema(data, schema)
            return StructuredResult(
                success=True, data=data, raw=raw, retries=retries_used
            )
        except ValueError as exc:
            if attempt < max_retries:
                # Append the failed response + error for the retry.
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your output failed validation: {exc}\n"
                            "Fix the error and return only valid JSON."
                        ),
                    }
                )
                retries_used += 1
            else:
                return StructuredResult(
                    success=False,
                    data=None,
                    raw=raw,
                    retries=retries_used,
                    error=str(exc),
                )

    # Should not reach here, but just in case.
    return StructuredResult(success=False, raw=raw, error="Unexpected state")


def _normalize_examples(
    examples: list[Example] | list[dict[str, Any]] | None,
) -> list[Example]:
    if not examples:
        return []
    result: list[Example] = []
    for ex in examples:
        if isinstance(ex, Example):
            result.append(ex)
        elif isinstance(ex, dict):
            result.append(Example(input=str(ex["input"]), output=ex["output"]))
        else:
            raise TypeError(f"Expected Example or dict, got {type(ex)}")
    return result


def _assemble_system_prompt(
    system_prompt: str,
    schema: dict[str, Any],
    examples: list[Example],
) -> str:
    """Build the full system prompt: instructions + schema + examples."""
    parts = [system_prompt.rstrip()]

    parts.append("\nJSON Schema your output must conform to:")
    parts.append(json.dumps(schema, indent=2, sort_keys=True))

    if examples:
        parts.append("\nExamples:")
        for i, ex in enumerate(examples, 1):
            parts.append(f"\nExample {i}:")
            parts.append(f"Input: {ex.input}")
            parts.append(f"Output: {json.dumps(ex.output, sort_keys=True)}")

    return "\n".join(parts)


async def _call_llm(
    llm_client: Any,
    config: dict[str, Any],
    tier: str,
    messages: list[dict[str, str]],
    *,
    attribution: str | None = None,
    purpose: str | None = None,
) -> str:
    """Call the injected LLM client, handling sync and async."""
    response = llm_client.complete(
        messages=messages,
        config=config,
        tier=tier,
        attribution=attribution,
        purpose=purpose,
    )
    if isawaitable(response):
        response = await response
    if not isinstance(response, str):
        raise ValueError("LLM response must be plain text")
    return response


# ---------------------------------------------------------------------------
# Low-level primitives (unchanged, kept for backwards compatibility)
# ---------------------------------------------------------------------------


async def structured_complete(
    llm_client: Any,
    config: dict[str, Any],
    tier: str,
    messages: list[dict[str, str]],
) -> str:
    """Call an injected LLM client and require a plain text response."""
    response = llm_client.complete(messages=messages, config=config, tier=tier)
    if isawaitable(response):
        response = await response
    if not isinstance(response, str):
        raise ValueError("LLM response must be plain text")
    return response


_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n?(?P<body>.*?)\n?\s*```\s*$",
    re.DOTALL,
)


def _strip_code_fences(text: str) -> str:
    """Strip a single Markdown code fence wrapping the entire response.

    Anthropic and Google models often wrap JSON output in ```json ... ```
    even when explicitly instructed to return raw JSON. This is a no-op for
    OpenAI responses which return raw JSON.
    """
    match = _CODE_FENCE_RE.match(text)
    if match:
        return match.group("body")
    return text


def parse_json_response(response_text: str) -> dict[str, Any]:
    """Parse an LLM response as a JSON object."""
    cleaned = _strip_code_fences(response_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError(f"LLM response is not valid JSON: {error}") from error

    if not isinstance(data, dict):
        raise ValueError("LLM response JSON must be an object")
    return data


def validate_json_schema(
    data: dict[str, Any],
    schema: dict[str, Any],
    label: str = "",
) -> None:
    """Validate a JSON object against a JSON Schema."""
    try:
        Draft202012Validator(schema).validate(data)
    except ValidationError as error:
        message = _format_validation_error(error)
        if label:
            message = f"{label}: {message}"
        raise ValueError(message) from error


def load_prompt(path: str | Path) -> str:
    """Read a prompt text file."""
    return Path(path).read_text(encoding="utf-8")


def load_schema(path: str | Path) -> dict[str, Any]:
    """Read a JSON Schema file as an object."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Schema file is not valid JSON: {error}") from error

    if not isinstance(data, dict):
        raise ValueError("Schema file JSON must be an object")
    return data


def _format_validation_error(error: ValidationError) -> str:
    path = ".".join(str(part) for part in error.path)
    if path:
        return f"{path}: {error.message}"
    return error.message
