---
phase: 2
blocked: false
state: plan
steps_remaining:
---

# Toolkit — Dev Plan

## Cold Start
Active module: **Prompt Regression** (extraction from diplomat project).
Load: ARCH_prompt_regression.md for contract, PROJECT.md for constraints, ARCHITECTURE.md for context.
Consumers: Diplomat (first consumer, migrating from local implementation), Phosphene (future).

### Gotchas
- **Running tests:** Use `/home/claude/toolkit-venv/bin/python3 -m pytest` (not bare `pytest` or `python3 -m pytest` — those hit system Python which has no pytest). The venv is inside the container at `/home/claude/toolkit-venv/`.
- **PYTHONPATH:** When running tests, set `PYTHONPATH=/home/claude/workspace/toolkit/src` so pytest can find the `toolkit` package, or use `cd /home/claude/workspace/toolkit && /home/claude/toolkit-venv/bin/python3 -m pytest`.

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
| Cost Accountant | Complete (Phase 1, 28 tests) |
| Prompt Regression | Phase 2 — extracting from diplomat |

## Phase 2: Prompt Regression — Extract from Diplomat

**Status:** Plan
**Regime:** Build

Scope: Extract the prompt regression framework (types, judge, runner) from `diplomat/tests/prompt_regression/` into `toolkit/prompt_regression/` as a reusable module. Then update diplomat to import from toolkit instead of its local copy. Reference: diplomat's `diplomat-testing-doc.md` §4.

**Source files (in diplomat):**
- `tests/prompt_regression/types.py` — dataclasses, scenario loading, JSON path helpers. Zero external deps.
- `tests/prompt_regression/judge.py` — LLMJudge. Uses `llm_client.complete()` interface.
- `tests/prompt_regression/runner.py` — ScenarioRunner. Has diplomat-specific `_call_module()` dispatch and `_default_module_builders()`.

**Key design decision:** The runner's `_call_module()` currently hardcodes how to call extraction, generation, analyst, and adversarial modules. For toolkit, this needs to become a pluggable callback so each consumer project provides its own module dispatch. The runner core (property evaluation, scenario loading, reporting) is fully generic.

Steps:

- [ ] 2.1 — **Create ARCH_prompt_regression.md.** Define the module contract: types (PropertyCheck, PropertyResult, ScenarioResult, RunReport, JudgeResult), LLMJudge interface, ScenarioRunner interface with pluggable `module_caller` callback, JSON path helpers, scenario loading. Document that the LLM judge uses the same `complete(messages, config, tier)` interface as `toolkit/llm_client`. Add the module to ARCHITECTURE.md component map.

- [ ] 2.2 — **Create `toolkit/prompt_regression/` with types and judge.** Copy `types.py` and `judge.py` from diplomat verbatim (they have zero diplomat dependencies). Create `toolkit/prompt_regression/__init__.py` with public exports. Add unit tests to toolkit's test suite: JSON path helpers (exists, get, edge cases) and judge parsing (PASS, FAIL, malformed, invalid verdict). Run toolkit regression.

- [ ] 2.3 — **Extract runner with pluggable module dispatch.** Create `toolkit/prompt_regression/runner.py`. The `ScenarioRunner` constructor accepts `module_caller: Callable[[str, Any, dict], Awaitable[Any]]` instead of hardcoding `_call_module()`. Move `_evaluate_property`, `_normalize_output`, `_judge_response_text`, `run_scenario`, `run_all` as-is. Remove diplomat-specific imports (`DecisionContext`, `RuleBasedExtractor`, `LLMGenerator`) and the `_default_module_builders` / CLI entry point — those stay in diplomat. Add a runner test with a fake module_caller. Run toolkit regression.

- [ ] 2.4 — **Update diplomat to consume from toolkit.** Replace diplomat's `tests/prompt_regression/types.py`, `judge.py`, and the generic parts of `runner.py` with imports from `toolkit.prompt_regression`. Keep diplomat's `tests/prompt_regression/` directory with: a thin `runner.py` that provides the diplomat-specific `module_caller` and CLI entry point, and the scenario JSON files. Update diplomat's test imports. Run diplomat's full 212-test regression.

- [ ] 2.5 — **Documentation and regression.** Verify both toolkit and diplomat test suites pass. Update toolkit ARCHITECTURE.md, DEVPLAN summary, DEVLOG. Update diplomat's `diplomat-testing-doc.md` to note the toolkit dependency. Transition to `state: review`.

## Phase 1: Cost Accountant — Core Implementation

**Status:** Complete. Core implementation finished with 28 tests passing; see DEVLOG 2026-05-17.
**Regime:** Build

Implemented typed cost budgets, pricing and estimates, append-only JSONL ledger I/O, budget-enforced `complete()` wrapping `llm_client`, rate-limit/spending-cap abort handling, reporting, public exports, and a 28-test suite.

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
| 2026-05-17 | Cost Accountant Phase 1 complete | Core implementation complete; 28 tests passing; blocked for human audit |
