---
phase: 1
blocked: false
state: execute
steps_remaining: 3
---

# Toolkit — Dev Plan

## Cold Start
Active module: **Cost Accountant** (sixth in implementation sequence).
Load: ARCH_cost_accountant.md for contract, PROJECT.md for constraints, ARCHITECTURE.md for context.
Consumers waiting: Phosphene (prerequisite for all future LLM operations — API spending cap hit, no LLM calls until accountant is in place).

### Key Context
- **Wraps llm_client:** Only cross-module dependency in toolkit. Consumers replace `llm_client.complete()` with `accountant.complete(budget=...)`.
- **Dependencies:** stdlib only (json, pathlib, datetime, dataclasses) + toolkit/llm_client
- **Ledger format:** Append-only JSONL. One line per call. Stable schema.
- **Budget enforcement:** per-call, per-operation, per-session. Three levels.
- **Abort on hard errors:** spending cap and rate limit errors → immediate abort, no retry.
- **Token estimation:** chars ÷ 4 heuristic (overestimates → conservative budgets).

## Current Status
| Module | Status |
|--------|--------|
| Embedding | Complete (43 tests) |
| Clustering | Complete (48 tests) |
| LLM Client | Complete |
| Telegram Client | Complete |
| JSON-RPC Client | Complete |
| Cost Accountant | **In progress** — Phase 1 active |

## Phase 1: Cost Accountant — Core Implementation

**Status:** In progress.
**Regime:** Build

### Implementation Notes
- `LLMRateLimitError` does not exist in llm_client — rate limit errors surface as `LLMAPIError` (status_code 429 or message match). Detect by checking `LLMAPIError.status_code == 429` or message contains "rate limit".
- Operation budgets are in-memory per session (reset on construction), not loaded from ledger.
- Session total also in-memory (reset on construction). `report()` reads ledger for historical data.
- Token estimation: `len(text) // 4` heuristic applied to concatenated message content.

### Steps

| Step | What | Status |
|------|------|--------|
| 1 | `types.py` + `errors.py` — all dataclasses, DEFAULT_PRICING, error hierarchy | Done |
| 2 | Constructor + ledger I/O — `__init__()`, `_append_entry()`, `_load_ledger()` | Done |
| 3 | Estimation — `estimate_cost()`, `estimate_batch()`, `_estimate_input_tokens()` | Pending |
| 4 | `complete()` — budget enforcement, llm_client wrapping, error detection, ledger write | Pending |
| 5 | `report()` + `session_total` — ledger analytics, anomaly detection | Pending |
| 6 | `__init__.py`, tests (≥20), pyproject.toml check | Pending |

### Exit Criteria
- `CostAccountant(ledger_path)` creates/opens JSONL ledger
- `estimate_cost(model, tokens)` returns `CostEstimate`; raises `UnknownModelError` for unknown model
- `estimate_batch(model, calls)` returns `BatchEstimate` with per-call breakdown
- `complete(messages, config, tier, budget)` enforces per-call, operation, and session budgets; raises `BudgetExceededError` subtypes when exceeded
- `complete()` aborts on rate limit / spending cap with `RateLimitAbortError` / `SpendingCapAbortError`
- `complete()` appends `LedgerEntry` to JSONL on every call (success or failure)
- `report()` reads ledger and returns breakdown by operation, model, date; includes anomalies
- `session_total` tracks in-memory cumulative since construction
- ≥20 tests passing

## Phase 3: RAPTOR recursive clustering — COMPLETE

**Status:** All steps complete. 48 tests passing (29 original + 19 new RAPTOR tests).
**Contract change:** Added `texts: list[str] | None = None` parameter to `cluster()` — required for RAPTOR, ignored for HDBSCAN.

**Regime:** Build

### Steps

| Step | What | Status |
|------|------|--------|
| 1 | Add `raptor_embedder` to ClusterConfig, update ARCH spec | Done |
| 2 | Implement `_cluster_raptor()` — single recursion level | Done |
| 3 | Multi-level recursion and depth limit | Done |
| 4 | Validation: missing summarizer/embedder/texts → error | Done |
| 5 | Full test suite for RAPTOR | Done (19 new tests) |

### Exit Criteria — All Met
- `cluster(embeddings, ClusterConfig(strategy=RAPTOR, raptor_summarizer=fn, raptor_embedder=fn), texts=texts)` returns tree ✓
- Missing callbacks or texts → ClusterStrategyError ✓
- Texts length mismatch → ClusterInputError ✓
- Recursion stops at max_depth or single cluster ✓
- labels maps original items to leaf-layer clusters ✓
- Original 29 tests unchanged and passing ✓

## Clustering — Completed Phases
- **Phase 1:** Types and HDBSCAN flat clustering — 24 tests. See DEVLOG 2026-04-24.
- **Phase 2:** UMAP dimensionality reduction — 5 new tests (29 total). See DEVLOG 2026-04-24.

## Embedding — Completed Phases
- **Phase 1:** Types and core embed function — 19 tests. See DEVLOG 2026-04-24.
- **Phase 2:** Similarity functions — 12 new tests (31 total). See DEVLOG 2026-04-24.
- **Phase 3:** Caching — 12 new tests (43 total). See DEVLOG 2026-04-24.

---

## Change History
| Date | What Changed | Why |
|------|-------------|-----|
| 2026-04-24 | Initial DEVPLAN.md | Track Embedding module implementation |
| 2026-04-24 | Embedding Phases 1-3 complete | Phase completion protocols |
| 2026-04-24 | Switched active module to Clustering | Cold start for next module |
| 2026-04-24 | Clustering Phase 1 complete | Phase completion protocol |
| 2026-04-24 | Clustering Phase 2 complete | Phase completion protocol |
| 2026-04-24 | Phase 3 plan approved (RAPTOR + raptor_embedder contract change) | Discuss-mode phase planning |
| 2026-04-30 | Phase 3 complete — RAPTOR recursive clustering implemented | 19 new tests (48 total). Added `texts` param to `cluster()`. |
| 2026-05-16 | Migrated frontmatter to e2e template schema (`phase`, `blocked`, `state`) | Wired toolkit into autonomous loop runner; active module = Cost Accountant, state = plan |
| 2026-05-16 | Phase 1 plan: 6-step cost_accountant implementation | state → execute; noted LLMRateLimitError gap (use LLMAPIError + status_code check) |
