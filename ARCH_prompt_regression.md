# ARCH: Prompt Regression

## Purpose
Reusable prompt regression test framework for projects that need scenario-based
checks over LLM-facing workflows. It loads JSON scenarios, invokes
consumer-provided module logic, evaluates deterministic properties, optionally
uses an LLM judge for semantic checks, and returns structured reports.

**Provenance:** Extracted from diplomat's `tests/prompt_regression/`
framework. Diplomat-specific module construction and CLI entry points remain in
diplomat; toolkit owns the generic types, judge, runner, JSON path helpers, and
reporting.

## Public API

### load_scenario
- **Signature:** `load_scenario(path: str | Path) -> dict[str, Any]`
- **Parameters:**
  - path: JSON scenario file path
- **Returns:** validated scenario dict
- **Errors:** `ValueError` — file is missing, invalid JSON, or missing required fields.

### load_scenarios
- **Signature:** `load_scenarios(directory: str | Path) -> list[dict[str, Any]]`
- **Parameters:**
  - directory: path to directory containing `*.json` scenario files (recursive)
- **Returns:** list of validated scenario dicts, sorted by filename
- **Errors:** `ValueError` if directory does not exist

### json_path_exists
- **Signature:** `json_path_exists(data: Any, path: str) -> bool`
- **Parameters:**
  - data: nested dict/list/scalar payload
  - path: dot/bracket path such as `patch.data.promises[0].status`
- **Returns:** True when the path resolves to a present value (including falsey values like `None`, `False`, `0`).

### json_path_get
- **Signature:** `json_path_get(data: Any, path: str) -> Any`
- **Parameters:** same as `json_path_exists`
- **Returns:** resolved value
- **Errors:** `KeyError` (missing key), `IndexError` (out of range), `TypeError` (wrong container type), `ValueError` (invalid path syntax)

### LLMJudge

Evaluates semantic properties by asking an injected LLM client for a verdict.

- **Constructor:** `LLMJudge(llm_client: Any, llm_config: dict[str, Any], tier: str = "commodity")`
  - llm_client: object exposing `complete(messages, config, tier)` returning plain str
  - llm_config: provider configuration dict passed through to the LLM client
  - tier: model tier string passed through to the LLM client

#### evaluate
- **Signature:** `async def evaluate(self, response_text: str, criteria: str, pass_instruction: str, fail_instruction: str, context: str = "") -> JudgeResult`
- **Returns:** `JudgeResult`
- **Errors:** `ValueError` if LLM response is not plain text or cannot be parsed as `PASS|explanation` / `FAIL|explanation`

The LLM client protocol intentionally matches `toolkit.llm_client.complete`:
`complete(messages, config, tier)`. Prompt Regression does not import
`toolkit.llm_client`; consumers pass the client/config they want.

### ScenarioRunner

Runs scenarios with consumer-provided module dispatch.

- **Constructor:** `ScenarioRunner(llm_client: Any, llm_config: dict[str, Any], module_caller: ModuleCaller)`
  - llm_client: LLM client for judge evaluations
  - llm_config: provider configuration dict
  - module_caller: async callback for project-specific module dispatch

```python
ModuleCaller = Callable[[str, Any, dict[str, Any]], Awaitable[Any]]
```

The callback receives:
- module name (str) from the scenario's `"module"` field
- input payload (dict) from the scenario's `"input"` field
- metadata dict (currently `{}`, reserved for future use)

It returns the raw module output. The runner normalizes dataclasses via `asdict()`.

#### run_scenario
- **Signature:** `async def run_scenario(self, scenario: dict[str, Any]) -> ScenarioResult`
- Runs one scenario, evaluates all properties, returns structured results.

#### run_all
- **Signature:** `async def run_all(self, scenario_dir: str | Path, module_filter: str | None = None) -> RunReport`
- Loads scenarios from directory, optionally filters by module name, runs each, prints per-scenario PASS/FAIL, returns aggregate report.

## Types

```python
@dataclass(frozen=True)
class PropertyCheck:
    type: str                          # "json_path_exists" | "json_path_equals" | "llm_judge"
    description: str
    path: str | None = None            # for json_path_* checks
    value: Any | None = None           # for json_path_equals
    criteria: str | None = None        # for llm_judge
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

@dataclass(frozen=True)
class JudgeResult:
    verdict: str                       # "PASS" or "FAIL"
    explanation: str
    criteria: str
```

## Scenario Format

```json
{
  "scenario_id": "extraction_promise_explicit_001",
  "module": "extraction",
  "description": "Explicit promise should create a pending promise entry",
  "input": {
    "text": "Alpha promises Beta to support the vote.",
    "current_state": {},
    "trigger_type": "message"
  },
  "expected_properties": [
    {
      "type": "json_path_exists",
      "description": "A promise entry exists",
      "path": "patch.data.promises[0]"
    },
    {
      "type": "json_path_equals",
      "description": "Promise status is pending",
      "path": "patch.data.promises[0].status",
      "value": "pending"
    },
    {
      "type": "llm_judge",
      "description": "Response declines the alliance",
      "criteria": "The response must not accept the alliance.",
      "pass_instruction": "Return PASS if the response declines.",
      "fail_instruction": "Return FAIL if it accepts."
    }
  ]
}
```

Required fields: `scenario_id`, `module`, `description`, `input` (dict), `expected_properties` (list).

## Property Types

- `json_path_exists` — `path` must resolve in normalized output. Requires `path`.
- `json_path_equals` — `path` must resolve to `value`. Requires `path` and `value`.
- `llm_judge` — judge must return PASS for the criteria. Requires `criteria`, `pass_instruction`, `fail_instruction`. Optional `path` extracts specific text for judging.

Unknown property types raise `ValueError`.

## Error Handling

- Scenario load errors (`ValueError`) are raised before execution.
- Module caller exceptions propagate — the runner does not catch module failures.
- `json_path_equals` path resolution errors are caught and produce a failed `PropertyResult` with the error as `actual`.
- `llm_judge` exceptions (LLM network errors, rate limits, malformed responses) are caught and produce a failed `PropertyResult` with `judge error: ...` as `actual`.
- The runner processes all scenarios even if individual ones fail — `RunReport` contains all results.

## State

No persistent state. Scenario loading reads JSON files; runner execution keeps
only per-run in-memory results. LLM usage, budgets, and rate limits are owned by
the injected LLM client or the consuming project.

## Usage Example

```python
from toolkit.prompt_regression import LLMJudge, ScenarioRunner, load_scenario

async def my_module_caller(module: str, input_data, metadata: dict):
    if module == "extraction":
        extractor = MyExtractor()
        return await extractor.extract(input_data["text"], {}, "message")
    raise ValueError(f"Unknown module: {module}")

runner = ScenarioRunner(
    llm_client=my_llm_client,
    llm_config=my_config,
    module_caller=my_module_caller,
)

report = await runner.run_all("tests/scenarios/")
print(f"{report.passed}/{report.total} passed")
```

## Design Notes

### Consumer Dispatch

Diplomat's original runner hardcoded module construction and calls for its own
extraction, generation, analyst, and adversarial modules. Toolkit replaces that
with `module_caller` so the runner remains reusable and has no consumer-domain
imports.

### LLM Client Coupling

The judge uses the `complete(messages, config, tier)` protocol but does not
import `toolkit.llm_client`. This preserves module independence and lets
consumers wrap, account for, or mock LLM calls.

---

## Change History
| Date | What Changed | Why |
|------|--------------|-----|
| 2026-05-28 | Initial ARCH — prompt regression extraction contract | Define reusable boundary before copying diplomat implementation |
| 2026-05-28 | Updated ARCH to match actual implementation | Worker's initial ARCH used different field names (Scenario dataclass, PropertyCheck.kind, etc.); aligned to diplomat's tested code (dict scenarios, PropertyCheck.type, etc.) |
