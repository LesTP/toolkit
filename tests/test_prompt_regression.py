"""Tests for toolkit.prompt_regression — types, judge, and runner."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import pytest

from toolkit.prompt_regression.judge import LLMJudge, _parse_judge_response
from toolkit.prompt_regression.runner import ScenarioRunner
from toolkit.prompt_regression.types import (
    PropertyResult,
    RunReport,
    ScenarioResult,
    json_path_exists,
    json_path_get,
    load_scenario,
)


# --- JSON path helpers ---


def test_json_path_get_simple_key():
    assert json_path_get({"a": 1}, "a") == 1


def test_json_path_get_nested():
    assert json_path_get({"a": {"b": 2}}, "a.b") == 2


def test_json_path_get_array_index():
    assert json_path_get({"items": [10, 20, 30]}, "items[1]") == 20


def test_json_path_get_nested_array():
    data = {"results": [{"name": "alice"}, {"name": "bob"}]}
    assert json_path_get(data, "results[1].name") == "bob"


def test_json_path_get_missing_key():
    with pytest.raises(KeyError):
        json_path_get({"a": 1}, "b")


def test_json_path_get_index_out_of_range():
    with pytest.raises(IndexError):
        json_path_get({"items": [1]}, "items[5]")


def test_json_path_get_type_error_not_dict():
    with pytest.raises(TypeError):
        json_path_get({"a": 1}, "a.b")


def test_json_path_get_type_error_not_list():
    with pytest.raises(TypeError):
        json_path_get({"a": "text"}, "a[0]")


def test_json_path_get_empty_path():
    with pytest.raises(ValueError):
        json_path_get({"a": 1}, "")


def test_json_path_exists_true():
    assert json_path_exists({"a": {"b": 0}}, "a.b") is True


def test_json_path_exists_false():
    assert json_path_exists({"a": 1}, "b") is False


def test_json_path_exists_false_on_none_value():
    # None is a present value — exists should return True
    assert json_path_exists({"a": None}, "a") is True


# --- load_scenario ---


def test_load_scenario_valid(tmp_path):
    scenario = {
        "scenario_id": "test.1",
        "description": "A test scenario.",
        "module": "extraction",
        "input": {"text": "hello"},
        "expected_properties": [
            {"type": "json_path_exists", "description": "has key", "path": "result"},
        ],
    }
    path = tmp_path / "test.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    loaded = load_scenario(path)
    assert loaded["scenario_id"] == "test.1"


def test_load_scenario_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_scenario(path)


def test_load_scenario_missing_field(tmp_path):
    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps({"description": "no id"}), encoding="utf-8")
    with pytest.raises(ValueError, match="scenario_id"):
        load_scenario(path)


# --- Judge parsing ---


def test_parse_judge_pass():
    verdict, explanation = _parse_judge_response("PASS|Looks good.")
    assert verdict == "PASS"
    assert explanation == "Looks good."


def test_parse_judge_fail():
    verdict, explanation = _parse_judge_response("FAIL|Missing constraint.")
    assert verdict == "FAIL"
    assert explanation == "Missing constraint."


def test_parse_judge_case_insensitive():
    verdict, _ = _parse_judge_response("pass|ok")
    assert verdict == "PASS"


def test_parse_judge_no_separator():
    with pytest.raises(ValueError, match="separator"):
        _parse_judge_response("MAYBE because unclear")


def test_parse_judge_invalid_verdict():
    with pytest.raises(ValueError, match="PASS or FAIL"):
        _parse_judge_response("MAYBE|it is unclear")


def test_parse_judge_blank_explanation():
    with pytest.raises(ValueError, match="blank"):
        _parse_judge_response("PASS|")


# --- LLMJudge ---


class FakeLLMClient:
    def __init__(self, response: str = "PASS|Looks good."):
        self.response = response
        self.calls: list[dict] = []

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_llm_judge_pass():
    async def _run():
        client = FakeLLMClient("PASS|Criteria met.")
        judge = LLMJudge(client, {}, tier="commodity")
        result = await judge.evaluate(
            response_text="Some response",
            criteria="Must be polite",
            pass_instruction="PASS if polite",
            fail_instruction="FAIL if rude",
        )
        assert result.verdict == "PASS"
        assert result.explanation == "Criteria met."
        assert len(client.calls) == 1
    asyncio.run(_run())


def test_llm_judge_fail():
    async def _run():
        client = FakeLLMClient("FAIL|Too aggressive.")
        judge = LLMJudge(client, {}, tier="commodity")
        result = await judge.evaluate(
            response_text="Some response",
            criteria="Must be polite",
            pass_instruction="PASS if polite",
            fail_instruction="FAIL if rude",
        )
        assert result.verdict == "FAIL"
    asyncio.run(_run())


# --- ScenarioRunner ---


@dataclass(frozen=True)
class FakeExtractionResult:
    success: bool = True
    patch: dict = None
    error: str | None = None

    def __post_init__(self):
        if self.patch is None:
            object.__setattr__(self, "patch", {
                "data": {"promises": [{"status": "pending", "from_faction": "Alpha"}]}
            })


async def fake_module_caller(module_name: str, input_data: Any, metadata: dict) -> Any:
    if module_name == "extraction":
        return FakeExtractionResult()
    raise ValueError(f"Unsupported module: {module_name}")


def test_runner_structural_check():
    async def _run():
        runner = ScenarioRunner(
            llm_client=FakeLLMClient(),
            llm_config={},
            module_caller=fake_module_caller,
        )
        scenario = {
            "scenario_id": "test.promise",
            "description": "Promise is pending.",
            "module": "extraction",
            "input": {"text": "Alpha promises Beta support."},
            "expected_properties": [
                {
                    "type": "json_path_equals",
                    "description": "Status is pending.",
                    "path": "patch.data.promises[0].status",
                    "value": "pending",
                }
            ],
        }
        result = await runner.run_scenario(scenario)
        assert result.passed is True
        assert result.scenario_id == "test.promise"
    asyncio.run(_run())


def test_runner_failing_check():
    async def _run():
        runner = ScenarioRunner(
            llm_client=FakeLLMClient(),
            llm_config={},
            module_caller=fake_module_caller,
        )
        scenario = {
            "scenario_id": "test.mismatch",
            "description": "Status mismatch.",
            "module": "extraction",
            "input": {"text": "anything"},
            "expected_properties": [
                {
                    "type": "json_path_equals",
                    "description": "Should be kept.",
                    "path": "patch.data.promises[0].status",
                    "value": "kept",
                }
            ],
        }
        result = await runner.run_scenario(scenario)
        assert result.passed is False
        assert result.properties[0].expected == "kept"
        assert result.properties[0].actual == "pending"
    asyncio.run(_run())


def test_runner_run_all(tmp_path):
    async def _run():
        scenario = {
            "scenario_id": "test.all",
            "description": "Batch test.",
            "module": "extraction",
            "input": {"text": "Alpha promises Beta."},
            "expected_properties": [
                {
                    "type": "json_path_exists",
                    "description": "Has promises.",
                    "path": "patch.data.promises[0]",
                }
            ],
        }
        (tmp_path / "test.json").write_text(json.dumps(scenario), encoding="utf-8")

        runner = ScenarioRunner(
            llm_client=FakeLLMClient(),
            llm_config={},
            module_caller=fake_module_caller,
        )
        report = await runner.run_all(tmp_path)
        assert report.total == 1
        assert report.passed == 1
        assert len(report.results) == 1
    asyncio.run(_run())
