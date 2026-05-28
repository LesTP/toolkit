from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROPERTY_TYPES = {"json_path_exists", "json_path_equals", "llm_judge"}


@dataclass(frozen=True)
class PropertyCheck:
    type: str
    description: str
    path: str | None = None
    value: Any | None = None
    criteria: str | None = None
    pass_instruction: str | None = None
    fail_instruction: str | None = None


@dataclass(frozen=True)
class PropertyResult:
    passed: bool
    description: str
    expected: Any | None = None
    actual: Any | None = None
    judge_explanation: str | None = None


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    description: str
    properties: list[PropertyResult]
    passed: bool


@dataclass(frozen=True)
class RunReport:
    results: list[ScenarioResult]
    total: int
    passed: int


def load_scenario(path: str | Path) -> dict[str, Any]:
    scenario_path = Path(path)
    try:
        parsed = json.loads(scenario_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Scenario is not valid JSON: {scenario_path}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Scenario must be a JSON object: {scenario_path}")

    _validate_scenario(parsed, scenario_path)
    return parsed


def load_scenarios(directory: str | Path) -> list[dict[str, Any]]:
    scenario_dir = Path(directory)
    if not scenario_dir.is_dir():
        raise ValueError(f"Scenario directory does not exist: {scenario_dir}")

    return [load_scenario(path) for path in sorted(scenario_dir.rglob("*.json"))]


def json_path_exists(data: Any, path: str) -> bool:
    try:
        json_path_get(data, path)
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    return True


def json_path_get(data: Any, path: str) -> Any:
    if not path:
        raise ValueError("JSON path must not be empty")

    current = data
    for token in _parse_path(path):
        if isinstance(token, str):
            if not isinstance(current, dict):
                raise TypeError(f"Expected object before '{token}'")
            if token not in current:
                raise KeyError(token)
            current = current[token]
        else:
            if not isinstance(current, list):
                raise TypeError(f"Expected array before index [{token}]")
            current = current[token]
    return current


def _validate_scenario(scenario: dict[str, Any], path: Path) -> None:
    for field in ("scenario_id", "description", "module"):
        if not isinstance(scenario.get(field), str) or not scenario[field].strip():
            raise ValueError(f"Scenario {path} must define nonblank '{field}'")

    if "input" not in scenario or not isinstance(scenario["input"], dict):
        raise ValueError(f"Scenario {path} must define object 'input'")

    properties = scenario.get("expected_properties")
    if not isinstance(properties, list):
        raise ValueError(f"Scenario {path} must define list 'expected_properties'")

    for index, property_data in enumerate(properties):
        _validate_property(property_data, path, index)


def _validate_property(property_data: Any, path: Path, index: int) -> None:
    prefix = f"Scenario {path} property {index}"
    if not isinstance(property_data, dict):
        raise ValueError(f"{prefix} must be an object")

    property_type = property_data.get("type")
    if property_type not in PROPERTY_TYPES:
        raise ValueError(f"{prefix} has unsupported type: {property_type}")

    if not isinstance(property_data.get("description"), str):
        raise ValueError(f"{prefix} must define string 'description'")

    if property_type in {"json_path_exists", "json_path_equals"}:
        if not isinstance(property_data.get("path"), str) or not property_data[
            "path"
        ].strip():
            raise ValueError(f"{prefix} must define nonblank 'path'")

    if property_type == "json_path_equals" and "value" not in property_data:
        raise ValueError(f"{prefix} must define 'value'")

    if property_type == "llm_judge":
        for field in ("criteria", "pass_instruction", "fail_instruction"):
            if not isinstance(property_data.get(field), str) or not property_data[
                field
            ].strip():
                raise ValueError(f"{prefix} must define nonblank '{field}'")


def _parse_path(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    for segment in path.split("."):
        if not segment:
            raise ValueError(f"Invalid empty path segment in '{path}'")

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(.*)$", segment)
        if not match:
            raise ValueError(f"Invalid path segment '{segment}'")

        tokens.append(match.group(1))
        remainder = match.group(2)
        while remainder:
            index_match = re.match(r"^\[(\d+)\](.*)$", remainder)
            if not index_match:
                raise ValueError(f"Invalid array index syntax in '{segment}'")
            tokens.append(int(index_match.group(1)))
            remainder = index_match.group(2)

    return tokens
