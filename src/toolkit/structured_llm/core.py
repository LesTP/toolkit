from __future__ import annotations

import json
from inspect import isawaitable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


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


def parse_json_response(response_text: str) -> dict[str, Any]:
    """Parse an LLM response as a JSON object."""
    try:
        data = json.loads(response_text)
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
