# ARCH: Cost Accountant

## Purpose
Cost tracking and budget enforcement for external API calls. Wraps `toolkit/llm_client` to provide pre-call cost estimation, per-call budget checking, append-only cost ledger, rate-limit/spending-cap abort, and session-level reporting. Consumers replace `llm_client.complete()` calls with `cost_accountant.complete()` to gain automatic cost governance. Optional — projects without pay-per-call APIs don't need it.

Motivated by: $60+ untracked spend, 175-minute retry loop against a spending cap, and destructive operations triggered without cost awareness. See `phosphene/DESIGN_COST_GOVERNANCE.md` for the full incident catalog.

## Public API

### Types

```python
@dataclass
class CostBudget:
    operation_name: str                    # e.g., "t2_to_t3_distillation"
    operation_budget_usd: float            # max spend for this operation
    session_budget_usd: float = 100.0      # max across all operations this session
    per_call_max_usd: float = 1.0          # reject any single call estimated above this
    abort_on_rate_limit: bool = True        # don't retry rate limit or spending cap errors
    abort_on_spending_cap: bool = True      # treat "usage limits reached" as hard stop

@dataclass
class CostEstimate:
    model: str
    input_tokens: int
    estimated_output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_usd: float

@dataclass
class BatchEstimate:
    calls: list[CallEstimate]
    total_usd: float

@dataclass
class CallEstimate:
    label: str
    input_tokens: int
    estimated_cost_usd: float

@dataclass
class LedgerEntry:
    timestamp: str                         # ISO 8601
    operation: str                         # from CostBudget.operation_name
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cumulative_session_usd: float
    budget_name: str
    budget_remaining_usd: float
    duration_ms: int
    success: bool
    error: str | None

@dataclass
class CostReport:
    total_calls: int
    total_spend_usd: float
    by_operation: dict[str, float]         # operation_name → total USD
    by_model: dict[str, float]             # model → total USD
    by_date: dict[str, float]              # YYYY-MM-DD → total USD
    anomalies: list[str]                   # warnings (long durations, repeated failures)
```

### Constructor

- **Signature:** `CostAccountant(ledger_path: Path, pricing: dict[str, ModelPricing] | None = None, default_budget: CostBudget | None = None)`
- **Parameters:**
  - ledger_path: Path — where to write the append-only JSONL ledger. Created if missing.
  - pricing: optional model pricing override. Defaults to built-in table.
  - default_budget: optional default budget used when `complete()` is called without an explicit budget. Defaults to $25 session / $25 operation / $2 per call.
- **Errors:** none

```python
@dataclass
class ModelPricing:
    input_per_mtok: float       # USD per million input tokens
    output_per_mtok: float      # USD per million output tokens
```

Built-in pricing (updatable):
```python
DEFAULT_PRICING = {
    # Anthropic
    "claude-sonnet-4-20250514": ModelPricing(3.0, 15.0),
    "claude-sonnet-4-6":       ModelPricing(3.0, 15.0),
    "claude-haiku-4-5":        ModelPricing(0.25, 1.25),
    "claude-opus-4":           ModelPricing(15.0, 75.0),
    # OpenAI
    "gpt-4.1":                ModelPricing(2.0, 8.0),
    "gpt-4.1-mini":           ModelPricing(0.4, 1.6),
    "gpt-4.1-nano":           ModelPricing(0.1, 0.4),
    "gpt-4o":                 ModelPricing(2.5, 10.0),
    "gpt-4o-mini":            ModelPricing(0.15, 0.6),
    "gpt-5.5":                ModelPricing(2.0, 8.0),
    "o3":                     ModelPricing(2.0, 8.0),
    "o3-mini":                ModelPricing(1.1, 4.4),
    "o4-mini":                ModelPricing(1.1, 4.4),
}
```

Unknown models (not in the pricing table) use conservative fallback pricing of $15/$75 per Mtok (matching the most expensive known model) rather than raising an error. This ensures budget enforcement is never bypassed by a model name mismatch.

### complete

- **Signature:** `complete(*, messages: list[Message], config: LLMConfig, tier: ModelTier, budget: CostBudget | None = None) -> LLMResponse`
- **Parameters:** same as `llm_client.complete()` plus optional `budget` (falls back to `default_budget` from constructor)
- **Returns:** `LLMResponse` (from `toolkit/llm_client`)
- **Errors:**
  - `BudgetExceededError` — estimated cost exceeds per-call, operation, or session budget
  - `SpendingCapAbortError` — API returned a spending cap / usage limit error
  - `RateLimitAbortError` — API returned a rate limit error and `abort_on_rate_limit` is True
  - All `llm_client` errors pass through

**Behavior:**

1. Resolve model name from `config.models` using `tier`
2. Estimate input tokens from messages (chars ÷ 4 as approximation)
3. Estimate cost from tokens × pricing
4. **Check per-call budget:** if estimated > `budget.per_call_max_usd` → raise `BudgetExceededError`
5. **Check operation budget:** if operation cumulative + estimated > `budget.operation_budget_usd` → raise `BudgetExceededError`
6. **Check session budget:** if session cumulative + estimated > `budget.session_budget_usd` → raise `BudgetExceededError`
7. Call `llm_client.complete(messages, config, tier)`
8. On success: compute actual cost from `response.token_usage`, append to ledger, update cumulative totals
9. On `LLMAPIError` with status code 429, or an error message containing "rate limit": append failure to ledger. If `abort_on_rate_limit` → raise `RateLimitAbortError`. Else re-raise.
10. On error containing "usage limits" or "spending cap": append failure to ledger. If `abort_on_spending_cap` → raise `SpendingCapAbortError`. Else re-raise.
11. On other errors: append failure to ledger, re-raise.

### estimate_cost

- **Signature:** `estimate_cost(model: str, input_tokens: int, expected_output_tokens: int = 1000) -> CostEstimate`
- **Parameters:**
  - model: model identifier
  - input_tokens: known or estimated input token count
  - expected_output_tokens: estimated output tokens (default 1000)
- **Returns:** `CostEstimate`
- **Errors:** None — unknown models use conservative fallback pricing ($15/$75 per Mtok)

### estimate_batch

- **Signature:** `estimate_batch(model: str, calls: list[dict], expected_output_tokens_per_call: int = 1000) -> BatchEstimate`
- **Parameters:**
  - model: model identifier
  - calls: list of `{"input_chars": int, "label": str}` — one per expected LLM call
  - expected_output_tokens_per_call: default output estimate per call
- **Returns:** `BatchEstimate` with per-call breakdown and total
- **Errors:** None — unknown models use fallback pricing

### report

- **Signature:** `report(since: datetime | None = None) -> CostReport`
- **Parameters:**
  - since: filter ledger entries to only include those after this timestamp. None = all.
- **Returns:** `CostReport` with breakdowns by operation, model, date, and anomalies
- **Errors:** none

### session_total

- **Property:** `session_total -> float`
- Returns cumulative USD spent in the current session (since accountant construction)

## Configuration

The accountant is configured at construction time. No environment variables — the consumer provides the ledger path and optional pricing override.

```python
# Simple usage
accountant = CostAccountant(ledger_path=Path("logs/cost_ledger.jsonl"))

# With custom pricing (e.g., for a new model not yet in defaults)
accountant = CostAccountant(
    ledger_path=Path("logs/cost_ledger.jsonl"),
    pricing={
        "claude-sonnet-4-6": ModelPricing(input_per_mtok=3.0, output_per_mtok=15.0),
        "my-new-model": ModelPricing(input_per_mtok=5.0, output_per_mtok=25.0),
    },
)
```

## Ledger Format

Append-only JSONL at `ledger_path`. One line per LLM call (successful or failed):

```json
{"timestamp":"2026-05-14T09:30:32Z","operation":"t2_to_t3.reflection_batch_3","model":"claude-sonnet-4-20250514","input_tokens":24000,"output_tokens":1800,"cost_usd":0.099,"cumulative_session_usd":2.34,"budget_name":"t2_to_t3","budget_remaining_usd":2.66,"duration_ms":4200,"success":true,"error":null}
```

The ledger is the source of truth for all cost reporting. It survives process restarts (the accountant reads it on construction to initialize cumulative totals for `report()`). Session totals reset on construction.

## State

- **Session cumulative:** in-memory float, reset on construction. Tracks total spend since this accountant instance was created.
- **Operation cumulative:** in-memory dict, operation_name → float. Tracks per-operation spend within this session.
- **Ledger file:** append-only JSONL on disk. Persists across sessions. Read on construction for `report()`, not for budget enforcement (budgets are per-session).
- No other state. No network calls. No background threads.

## Dependencies

- `toolkit/llm_client` — the accountant wraps `complete()`. It imports `LLMConfig`, `ModelTier`, `Message`, `LLMResponse`, and `LLMAPIError` for rate-limit detection.
- Standard library only beyond that (json, pathlib, datetime, dataclasses).

## Coupling Notes

- **llm_client ↔ cost_accountant:** cost_accountant depends on llm_client. llm_client does not know about cost_accountant. This is the only toolkit cross-module dependency. It's one-way and optional — consumers that don't need cost tracking use llm_client directly.
- **Consumer integration:** consumers replace `from toolkit.llm_client import complete` with `from toolkit.cost_accountant import CostAccountant` and route calls through the accountant instance. The accountant passes through to llm_client internally.
- **Ledger format is stable.** The JSONL format is the contract with `tools/cost_report.py` and any future reporting tools. Fields can be added but not removed or renamed.

## Usage Example

```python
from toolkit.cost_accountant import CostAccountant, CostBudget
from toolkit.llm_client import LLMConfig, ModelTier, Message

accountant = CostAccountant(ledger_path=Path("logs/cost_ledger.jsonl"))

# Pre-operation: estimate and display
estimate = accountant.estimate_batch(
    model="claude-sonnet-4-20250514",
    calls=[
        {"input_chars": 83000, "label": "reflection_batch_1"},
        {"input_chars": 96000, "label": "reflection_batch_2"},
        # ... 7 more batches
    ],
    expected_output_tokens_per_call=2000,
)
print(f"Estimated cost: ${estimate.total_usd:.2f}")
# Human reviews and approves

# Set budget
budget = CostBudget(
    operation_name="t2_to_t3_distillation",
    operation_budget_usd=5.00,
    per_call_max_usd=1.00,
)

# Make calls (budget-checked, ledger-logged)
for batch in reflection_batches:
    response = accountant.complete(
        messages=batch.messages,
        config=llm_config,
        tier=ModelTier.QUALITY,
        budget=budget,
    )
    # If over budget: raises BudgetExceededError
    # If rate limited: raises RateLimitAbortError
    # If spending cap: raises SpendingCapAbortError

# Post-operation: report
print(f"Session total: ${accountant.session_total:.2f}")
report = accountant.report()
for op, cost in report.by_operation.items():
    print(f"  {op}: ${cost:.2f}")
```

## Error Hierarchy

```
CostAccountantError (base)
├── BudgetExceededError        — estimated cost exceeds configured budget
│   ├── PerCallBudgetError     — single call too expensive
│   ├── OperationBudgetError   — operation cumulative exceeded
│   └── SessionBudgetError     — session cumulative exceeded
├── SpendingCapAbortError      — API reported account spending cap reached
├── RateLimitAbortError        — API rate limit and abort_on_rate_limit=True
└── UnknownModelError          — model not found in pricing table (kept for backwards compat; estimate_cost no longer raises it)
```

## Token Estimation

Anthropic does not provide a public tokenizer library. The accountant uses a simple heuristic:

```python
estimated_tokens = len(text) // 4  # ~4 chars per token on average
```

This overestimates for English text (~3.5 chars/token) and underestimates for non-Latin scripts. For budget enforcement, overestimating is safer — it prevents budget overruns at the cost of slightly conservative limits.

If more accurate estimation is needed in the future, the accountant can be extended with a `token_counter` callback in its constructor.
