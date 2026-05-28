---
phase: 2
blocked: false
state: execute
steps_remaining: 5
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
- **Extraction source:** `diplomat/tests/prompt_regression/` is the source implementation.
- **Dependencies:** stdlib only for types and runner; judge accepts an injected LLM client with `complete(messages, config, tier)`.
- **Consumer dispatch:** Toolkit runner must use a pluggable `module_caller` callback; diplomat keeps domain-specific module wiring.
- **Scenario contract:** JSON scenario files define module input plus property checks; toolkit owns loading, JSON path helpers, judging, and reporting.
- **Migration target:** Diplomat becomes the first consumer; Phosphene is the future second consumer.

## Current Status
| Module | Status |
|--------|--------|
| Embedding | Complete (43 tests) |
| Clustering | Complete (48 tests) |
| LLM Client | Complete |
| Telegram Client | Complete |
| JSON-RPC Client | Complete |
| Cost Accountant | Complete (Phase 1, 28 tests) |
| Prompt Regression | Complete (Phase 2, 26 tests) |

## Phase 2: Prompt Regression — Extract from Diplomat

**Status:** Complete
**Regime:** Build

Extracted prompt regression framework from diplomat into `toolkit/prompt_regression/` — types, judge, runner with pluggable `module_caller` dispatch, 26 tests. Updated diplomat to import from toolkit (thin re-exports + diplomat-specific module caller). Both test suites pass (26 toolkit, 212 diplomat).

Steps:

- [x] 2.1 — **Create ARCH_prompt_regression.md.** Defined module contract. Added to ARCHITECTURE.md.
- [x] 2.2 — **Create `toolkit/prompt_regression/` with types and judge.** Copied verbatim from diplomat (zero diplomat deps).
- [x] 2.3 — **Extract runner with pluggable module dispatch.** `ScenarioRunner` accepts `module_caller` callback instead of hardcoded diplomat dispatch.
- [x] 2.4 — **Update diplomat to consume from toolkit.** types.py and judge.py are thin re-exports; runner.py keeps diplomat-specific `diplomat_module_caller` and CLI.
- [x] 2.5 — **Documentation and regression.** ARCH updated to match implementation, both test suites pass.

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
| 2026-05-28 | Phase 2 plan: prompt_regression extraction | state → execute; runner dispatch will be consumer-provided via callback |
