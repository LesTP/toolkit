---
phase: 4
blocked: true
state: close
steps_remaining: 0
---

# Toolkit — Dev Plan

## Cold Start
Active module: **Clankmates Client** (Phase 4 complete; see DEVLOG 2026-06-11).
Load: CLANKMATES_CLIENT_PLAN.md for plan, ARCHITECTURE.md for context, PROJECT.md for constraints.
Consumers: Diplomat (arena host + player), Clanker Courts (game_transport adapter).

### Gotchas
- **Running tests:** Use `/home/claude/toolkit-venv/bin/python3 -m pytest` (not bare `pytest` or `python3 -m pytest` — those hit system Python which has no pytest). The venv is inside the container at `/home/claude/toolkit-venv/`.
- **PYTHONPATH:** When running tests, set `PYTHONPATH=/home/claude/workspace/toolkit/src` so pytest can find the `toolkit` package, or use `cd /home/claude/workspace/toolkit && /home/claude/toolkit-venv/bin/python3 -m pytest`.
- **jsonschema missing from venv:** The toolkit venv is read-only. To test `structured_llm`: `pip install --target=/tmp/toolkit-deps jsonschema` then `PYTHONPATH=/home/claude/workspace/toolkit/src:/tmp/toolkit-deps pytest tests/structured_llm/`.

### Key Context
- **Vendor source:** `p:\shared\clanker-courts-player-client\skills\clanker-courts-operator\scripts\clanker_courts_player\`
- **Submodules:** `subprocess.py` (vendored wrapper), `decode.py` (message decoders), `cursor.py` (thread cursor store), `screen.py` (peer-DM screening rules)
- **Record vendor commit hash** in `subprocess.py` module docstring for upstream diff tracking.
- **`p:\shared` not mounted in container:** Vendor SKILL.md and upstream source files at `p:\shared\...` are inaccessible from the worker. Implement from the ARCH/PLAN spec instead; note in DEVLOG that the SKILL.md source was unavailable so the spec drove the implementation.

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
| Structured LLM | Complete (Phase 3) |
| Clankmates Client | Complete (Phase 4 close; see DEVLOG 2026-06-11) |

## Phase 4: Clankmates Client — Vendor + Extend from clanker-courts-player-client

**Status:** Complete — see DEVLOG 2026-06-11.
**Summary:** Host-side ops shipped, review was clean, and the phase closed at 88/88 tests passing.
**Regime:** Build
**Plan:** `CLANKMATES_CLIENT_PLAN.md`

## Phase 3: Structured LLM — Extract from Diplomat

**Status:** Complete. 22 tests passing. See DEVLOG 2026-06-10.
**Regime:** Build

Extracted structured LLM utilities (structured_complete, parse_json_response, validate_json_schema, load_prompt, load_schema) into `toolkit/structured_llm/`. Updated 6 diplomat call sites to import from toolkit. API.md supersedes per-consumer vendored deps (step 3.4). All tests pass (22 toolkit structured_llm).

**The duplicated pattern (4 copies in diplomat):**
- `_complete()` — call `llm_client.complete(messages, config, tier)`, await if needed, verify str response. Identical in analyst, adversarial, generation; extraction has a slight variant.
- `parse_json_object()` — `json.loads()` → dict, raise `ValueError` on failure. Lives in extraction, imported by analyst + adversarial.
- `validate_*(data, schema)` — `Draft202012Validator(schema).validate(data)`, format `ValidationError` with path. Nearly identical in all four modules — only the error message prefix differs.
- `load_prompt()` / `load_schema()` — read text file, parse JSON for schema. Lives in extraction, imported by analyst + adversarial.

**What toolkit gets:**
- `structured_complete(llm_client, config, tier, messages)` — async LLM call with `isawaitable` handling, plain-str verification
- `parse_json_response(response_text)` — parse JSON string → dict with clear error
- `validate_json_schema(data, schema, label="")` — validate dict against JSON schema, format error with path and label
- `load_prompt(path)` / `load_schema(path)` — file I/O helpers

**What stays in diplomat:** Domain-specific result types (`ExtractionResult`, `AnalysisResult`, `AdversarialResult`, `GenerationResult`), `_build_messages()` methods, module constructors, domain-specific validation wrappers (e.g., `validate_state_patch` wrapping the generic validator + returning `StatePatch`).

**Dependencies:** `jsonschema` (stdlib-external). The module uses the same injected LLM client protocol as prompt_regression — `complete(messages, config, tier)` returning plain str.

Steps:

- [x] 3.1 — **Create ARCH_structured_llm.md and update ARCHITECTURE.md.** Define the module contract: `structured_complete`, `parse_json_response`, `validate_json_schema`, `load_prompt`, `load_schema`. Document that the LLM client protocol matches `toolkit/llm_client` but is injected, not imported.

- [x] 3.2 — **Create `toolkit/structured_llm/` module.** Implement `__init__.py`, `core.py` with the five functions extracted from diplomat. All functions are standalone (no classes needed). `validate_json_schema` takes an optional `label` parameter for error message prefixing (replaces diplomat's per-module "State patch failed..." / "Intelligence report failed..." variants). Add unit tests: parse valid/invalid JSON, schema validation pass/fail with path formatting, load_prompt/load_schema, structured_complete with fake client. Run toolkit regression.

- [x] 3.3 — **Update diplomat to use toolkit utilities.** Replace diplomat's local copies:
  - `extraction/__init__.py`: replace `parse_json_object`, `load_prompt`, `load_schema`, `validate_state_patch` body with imports from `toolkit.structured_llm`
  - `analyst/__init__.py`: replace `validate_intelligence_report` body, remove `parse_json_object` import from extraction, replace `_complete()` with `structured_complete`
  - `adversarial/__init__.py`: same as analyst — replace validate + complete
  - `generation/__init__.py`: replace `_complete()` with `structured_complete` if applicable (generation has review-gate JSON parsing which is different)
  - Keep all domain types and `_build_messages()` unchanged
  - Update diplomat tests — fakes may need adjustment if `_complete` signature changed
  - Run diplomat full regression (212 tests)

  Verified 2026-06-10: 6 diplomat call sites import from `toolkit.structured_llm` (adversarial, analyst, extraction, generation, reconciliation, tools/scenario_compiler).

- [~] 3.4 — **Generate `deps/toolkit_api.md` for diplomat.** ~~Create the vendored contract file covering all toolkit modules diplomat depends on...~~

  **Superseded 2026-06-10 by `p:\shared\toolkit\API.md`.** The single-canonical-doc-in-toolkit approach replaces the per-consumer vendored-deps idea: one source of truth (no N-way drift), consumers attach `API.md` to sessions ad-hoc. Maintenance now governed by `PROJECT.md` Constraints ("API contract doc" bullet — update alongside any public-symbol change).

- [x] 3.5 — **Documentation and regression.** Verify both toolkit and diplomat test suites pass. Update toolkit ARCHITECTURE.md, DEVPLAN summary. Transition to `state: review`.

  Completed 2026-06-10: ARCHITECTURE.md Implementation Sequence updated (Structured LLM "In progress" → "Complete"); frontmatter transitioned to `state: review`; API.md added to `.llms/rules/toolkit.md` Always Loaded; PROJECT.md Constraints updated with API.md maintenance rule.

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
| 2026-05-28 | Phase 3 plan: structured_llm extraction | state -> execute; reusable LLM JSON/schema helpers will be extracted from diplomat |
| 2026-06-10 | Phase 4 queued: clankmates_client — sub-steps 4.1, 4.3, 4.4, 4.5 (vendor + decode + cursor + screen) | Vendor source: `p:\shared\clanker-courts-player-client` (2026-06-10 HEAD). Sub-step 4.2 (host ops) deferred pending arena Phase A; 4.6 (governance) deferred to end. Full plan: `CLANKMATES_CLIENT_PLAN.md`. Second consumer (CC) confirmed by operator. |
| 2026-06-10 | Phase 3 closed: structured_llm complete (state → review) | 3.3 verified by code inspection (6 diplomat call sites import from `toolkit.structured_llm`); 3.4 superseded by `toolkit/API.md` (single canonical contract surface replaces per-consumer vendoring; maintenance rule added to PROJECT.md Constraints); 3.5 doc cleanup done (ARCHITECTURE.md status → Complete, `.llms/rules/toolkit.md` Always Loaded includes API.md). |
| 2026-06-10 | Phase 4 closed: clankmates_client queued steps complete (43 tests) | Steps 4.1 (subprocess), 4.3 (decode), 4.4 (cursor), 4.5 (screen) shipped. Steps 4.2 (host ops) and 4.6 (governance) remain deferred. ARCH updated; gotcha added for `p:\shared` inaccessibility. |
| 2026-06-11 | Phase 4 reopened: step 4.2 queued (host ops) | Arena Phase A completed `CLANKMATES_NOTES.md` from live CLI smoke; full host-side surface now documented. Step 4.2 spec adopted from `CLANKMATES_CLIENT_PLAN.md` Phase 2 (refined post-smoke). Includes breaking-but-additive `send`/`reply` signature expansion for typed-inbox payload support. state → execute. |
