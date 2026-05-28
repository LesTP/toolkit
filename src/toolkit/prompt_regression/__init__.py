"""Reusable prompt regression test framework.

Scenario loading, JSON path property checks, LLM-as-judge evaluation,
and run reporting. Consumer projects provide module dispatch via callback.
"""

from toolkit.prompt_regression.judge import JudgeResult, LLMJudge
from toolkit.prompt_regression.runner import ModuleCaller, ScenarioRunner
from toolkit.prompt_regression.types import (
    PROPERTY_TYPES,
    PropertyCheck,
    PropertyResult,
    RunReport,
    ScenarioResult,
    json_path_exists,
    json_path_get,
    load_scenario,
    load_scenarios,
)

__all__ = [
    "JudgeResult",
    "LLMJudge",
    "ModuleCaller",
    "PROPERTY_TYPES",
    "PropertyCheck",
    "PropertyResult",
    "RunReport",
    "ScenarioResult",
    "ScenarioRunner",
    "json_path_exists",
    "json_path_get",
    "load_scenario",
    "load_scenarios",
]
