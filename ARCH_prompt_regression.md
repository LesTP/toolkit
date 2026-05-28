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
- **Signature:** `load_scenario(path: str | Path) -> Scenario`
- **Parameters:**
  - path: JSON scenario file path
- **Returns:** `Scenario`
- **Errors:**
  - `ScenarioLoadError` — file is missing, invalid JSON, or missing required
    fields.

### json_path_exists
- **Signature:** `json_path_exists(data: Any, path: str) -> bool`
- **Parameters:**
  - data: nested dict/list/scalar payload
  - path: dot/bracket path such as `answer.text`, `items[0].id`, or `$.status`
- **Returns:** True when the path resolves to a present value, including falsey
  values like `None`, `False`, `0`, or `""`.

### json_path_get
- **Signature:** `json_path_get(data: Any, path: str, default: Any = None) -> Any`
- **Parameters:** same as `json_path_exists`
- **Returns:** resolved value, or `default` when the path is absent.

### LLMJudge

Evaluates semantic properties by asking an injected LLM client for a verdict.

- **Constructor:** `LLMJudge(llm_client: Any, config: Any, *, tier: Any = None)`
  - llm_client: object exposing `complete(messages, config, tier)`
  - config: provider configuration passed through to the LLM client
  - tier: optional model tier passed through to the LLM client

#### judge
- **Signature:** `async def judge(self, output: Any, property_check: PropertyCheck, scenario: Scenario) -> JudgeResult`
- **Returns:** `JudgeResult`
- **Errors:** Judge and LLM failures are captured as failing `JudgeResult`
  values so a scenario report can include the failure.

The LLM client protocol intentionally matches `toolkit.llm_client.complete`:
`complete(messages, config, tier)`. Prompt Regression does not import
`toolkit.llm_client`; consumers pass the client/config they want.

### ScenarioRunner

Runs scenarios with consumer-provided module dispatch.

- **Constructor:** `ScenarioRunner(module_caller: ModuleCaller, *, judge: LLMJudge | None = None)`
  - module_caller: async callback that performs project-specific module work
  - judge: optional semantic judge for LLM-backed property checks

```python
ModuleCaller = Callable[[str, Any, dict[str, Any]], Awaitable[Any]]
```

The callback receives:
- module name from the scenario
- scenario input payload
- scenario metadata/options dict

It returns the raw module output. The runner normalizes that output for property
evaluation and reporting.

#### run_scenario
- **Signature:** `async def run_scenario(self, scenario: Scenario) -> ScenarioResult`
- Runs one scenario, evaluates all properties, and returns structured results.

#### run_all
- **Signature:** `async def run_all(self, scenarios: list[Scenario]) -> RunReport`
- Runs scenarios in order and returns aggregate counts plus per-scenario
  results.

## Types

```python
@dataclass
class Scenario:
    id: str
    module: str
    input: Any
    properties: list[PropertyCheck]
    metadata: dict[str, Any]

@dataclass
class PropertyCheck:
    name: str
    kind: str
    path: str | None = None
    expected: Any = None
    prompt: str | None = None
    required: bool = True

@dataclass
class JudgeResult:
    passed: bool
    verdict: str
    reason: str
    raw_response: str

@dataclass
class PropertyResult:
    property_name: str
    passed: bool
    reason: str
    expected: Any = None
    actual: Any = None
    judge_result: JudgeResult | None = None

@dataclass
class ScenarioResult:
    scenario_id: str
    module: str
    passed: bool
    output: Any
    properties: list[PropertyResult]
    error: str | None = None

@dataclass
class RunReport:
    total: int
    passed: int
    failed: int
    results: list[ScenarioResult]
```

## Scenario Format

```json
{
  "id": "generation_contains_claim",
  "module": "generation",
  "input": {"topic": "budget policy"},
  "metadata": {"case": "smoke"},
  "properties": [
    {"name": "has_text", "kind": "exists", "path": "text"},
    {"name": "mentions_budget", "kind": "equals", "path": "topic", "expected": "budget policy"},
    {"name": "is_neutral", "kind": "llm", "prompt": "Output should be politically neutral."}
  ]
}
```

Required fields are `id`, `module`, `input`, and `properties`. `metadata`
defaults to `{}`.

## Property Kinds

- `exists` — `path` must resolve in normalized output.
- `equals` — `path` must resolve to `expected`.
- `contains` — resolved value must contain `expected`.
- `llm` — `judge` must return a passing verdict for the property prompt.

Unknown property kinds fail the property with a clear reason.

## Outputs

Runner output is structured dataclasses, not printed text. Consumers decide how
to render reports in CI, CLIs, or project dashboards.

## State

No persistent state. Scenario loading reads JSON files; runner execution keeps
only per-run in-memory results. LLM usage, budgets, and rate limits are owned by
the injected LLM client or the consuming project.

## Usage Example

```python
from toolkit.prompt_regression import LLMJudge, ScenarioRunner, load_scenario

async def call_module(module: str, input_payload, metadata: dict):
    if module == "generation":
        return await generator.generate(input_payload)
    raise ValueError(f"Unknown module: {module}")

judge = LLMJudge(llm_client, llm_config, tier=model_tier)
runner = ScenarioRunner(call_module, judge=judge)

scenario = load_scenario("scenarios/generation_smoke.json")
result = await runner.run_scenario(scenario)
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

### Error Handling

Scenario load errors are raised before execution. Per-scenario module,
property, and judge failures are recorded in `ScenarioResult` /
`PropertyResult` so a full run can report all failures instead of stopping at
the first failing scenario.

---

## Change History
| Date | What Changed | Why |
|------|--------------|-----|
| 2026-05-28 | Initial ARCH — prompt regression extraction contract | Define reusable boundary before copying diplomat implementation |
