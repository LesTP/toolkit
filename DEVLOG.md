# Toolkit — Dev Log

## 2026-05-28 — Structured LLM Phase 3 planned

**Module:** Structured LLM | **Phase:** 3 | **Regime:** Build | **Result:** plan moved to execution

Registered Structured LLM in the toolkit architecture and moved the phase into
execution. The phase will extract diplomat's repeated LLM completion, JSON
parsing, JSON Schema validation, and prompt/schema loading helpers into a leaf
`toolkit.structured_llm` module with an injected client protocol.

### Step 3.1: Structured LLM architecture contract
Mode: Build
Outcome: Complete
Contract changes: Added `ARCH_structured_llm.md`; ARCHITECTURE.md lists Structured LLM as an in-progress leaf module.

Created the structured LLM module contract before implementation. The ARCH
defines `structured_complete`, `parse_json_response`, `validate_json_schema`,
`load_prompt`, and `load_schema`, and documents that LLM access is injected via
the `complete(messages, config, tier)` protocol instead of importing
`toolkit.llm_client`.

### Step 3.2: Structured LLM module implementation
Mode: Build
Outcome: Complete
Contract changes: Added `toolkit.structured_llm` public API and declared `jsonschema` as a runtime dependency.

Implemented `structured_complete`, `parse_json_response`,
`validate_json_schema`, `load_prompt`, and `load_schema` in
`src/toolkit/structured_llm/`. Added 13 unit tests covering JSON parsing,
schema validation path/label formatting, file loaders, sync and async fake LLM
clients, and non-text response rejection.

Verification:
- `tests/structured_llm/`: 13 passed
- `tests/test_prompt_regression.py`: 26 passed
- `tests/cost_accountant/`: 28 passed
- `tests/llm_client/`: 29 passed

Full `pytest` was not usable in this environment: `jsonschema` had to be
installed into a temporary local target because the shared venv is not
writable, `numpy` is absent for embedding/clustering, and collecting all test
directories together hits existing duplicate `test_core.py` module-name
collisions. The temporary dependency target was removed after verification.

---

## 2026-05-29 — structured_llm: strip Markdown code fences in parse_json_response

**Module:** structured_llm | **Regime:** Patch | **Result:** 19 tests passing (no regression)

**Contract changes:** `ARCH_structured_llm.md` — `parse_json_response` now strips a single surrounding Markdown code fence (` ```json ... ``` ` or ` ``` ... ``` `) before parsing. Updated "Out of Scope" to clarify that fence stripping IS done but partial extraction from prose is not.

### What was built
- `_strip_code_fences(text)` helper using a `^...$` DOTALL regex that requires the fence to wrap the entire response (rejects "Here is the JSON: { ... }" style outputs).
- `parse_json_response` calls `_strip_code_fences` before `json.loads`.
- No-op for OpenAI responses (which return raw JSON).

### Why
Anthropic (Claude) and Google (Gemini) wrap JSON output in ` ```json ... ``` ` even when the system prompt explicitly requests raw JSON. Before this fix, `structured_call`'s retry loop saw `json.loads` fail silently, retried, hit `max_retries`, and propagated `success=False` with no visible LLM error in the call log. Downstream Diplomat modules received nothing despite the LLM having generated valid (if wrapped) content.

Surfaced during Diplomat's Run 8 multi-provider self-play (3 providers playing the same scenario; before the fix only the OpenAI faction's messages reached the transcript).

### What this is NOT
- No JSON repair (mismatched braces, trailing commas, etc. still fail).
- No partial extraction from prose. Responses like "I propose this: `{...}`" still raise.
- No provider-specific normalization elsewhere. The fence-strip is the only response munging in this layer.

### Verification
- `pytest tests/structured_llm/` — 19 passed.
- Diplomat Run 8 (gpt-4.1-mini + claude-haiku-4-5 + gemini-2.5-flash on the Water Rights scenario) — all three providers now reach the transcript; 11/12 expected messages exchanged (1 lost to a Google free-tier rate limit, unrelated).

---

## 2026-06-10 — structured_llm: phase review

**Module:** structured_llm | **Phase:** 3 Review | **Result:** 22 tests passing

**Review findings applied:**
- Removed unused `field` import from `dataclasses` (dead import, must-fix)
- Removed unreachable fallback `return StructuredResult(success=False, error="Unexpected state")` at end of `structured_call` retry loop — the loop always returns inside itself (should-fix)
- Added 3 tests for `parse_json_response` code-fence stripping: `json`-tagged fence, plain fence, prose-with-embedded-JSON rejection — key behavior per ARCH spec was untested (should-fix)

**State transition:** review → close

---

## 2026-06-10 — Structured LLM Phase 3 complete

**Module:** Structured LLM | **Phase:** 3 | **Regime:** Build | **Result:** 22 tests passing

Extracted `structured_complete`, `parse_json_response`, `validate_json_schema`,
`load_prompt`, and `load_schema` from diplomat into `toolkit/structured_llm/`.
Updated 6 diplomat call sites (adversarial, analyst, extraction, generation,
reconciliation, scenario_compiler) to import from toolkit. Step 3.4 (per-consumer
vendored deps) superseded by `API.md` single-canonical-doc approach.

**Review cleanup:** Removed dead `field` import and unreachable fallback return from
`structured_call`. Added 3 code-fence tests covering the fence-stripping branch that
was untested before review.

**Gotcha extracted:** `jsonschema` is not installed in the toolkit venv (venv is
read-only). To run structured_llm tests: install to a temp dir and add to PYTHONPATH:
`pip install --target=/tmp/toolkit-deps jsonschema` then
`PYTHONPATH=.../src:/tmp/toolkit-deps pytest tests/structured_llm/`.

---

## 2026-06-10 — Clankmates Client Phase 4 planned

**Module:** Clankmates Client | **Phase:** 4 | **Regime:** Build | **Result:** Plan committed

Activated Phase 4: `clankmates_client`. Steps 4.1, 4.3, 4.4, 4.5 queued (player-side wrapper, decode, cursor, screen). Host-side ops (4.2) deferred pending arena Phase A. Governance (4.6) deferred pending 4.2 + arena Phase C contract.

ARCHITECTURE.md updated (Component Map + Implementation Sequence row 14). DECISIONS.md D-8 records scope rationale (vendor now; host-side deferred).

## 2026-06-10 — Clankmates Client Step 4.1

### Step 4.1: Module skeleton + vendored player-side wrapper
Mode: Build
Outcome: Passed 6/6 targeted tests for `tests/clankmates_client/test_subprocess.py`.
Contract changes: Added `src/toolkit/clankmates_client/__init__.py`, `src/toolkit/clankmates_client/subprocess.py`, `ARCH_clankmates_client.md`, and the new `toolkit.clankmates_client` section in `API.md`.

Vendored the upstream synchronous `clankm` wrapper into `toolkit.clankmates_client.subprocess` with the preserved `ClankmatesError` payload and `_run_json` error handling path. Added the source attribution and upstream commit hash to the module docstring, and ported the upstream test pattern to a fake-runner regression suite under `tests/clankmates_client/`.

The new package is deliberately small: it exposes only the client and error types for now, keeping later decode/cursor/screen work in the queued phase-4 steps.

## 2026-06-10 — Clankmates Client Step 4.3

### Step 4.3: `decode` submodule
Mode: Build
Outcome: Passed 13/13 `tests/clankmates_client` tests after adding the decode helpers and fixture suite.
Contract changes: Added `src/toolkit/clankmates_client/decode.py`, `tests/clankmates_client/test_decode.py`, vendored decode fixtures under `tests/clankmates_client/fixtures/`, and updated `ARCH_clankmates_client.md` plus `API.md`.

Split the generic Clankmates message helpers out of the upstream player-client `messages.py` pattern into a leaf `decode` module: `decode_clankmates_message`, `message_timestamp`, `filter_by_body_type`, and `latest_by_timestamp`. Kept the game-specific selectors out of the toolkit as planned, and used vendored inbox fixtures to cover both timestamp ordering and body-type filtering.

## 2026-06-10 — Clankmates Client Step 4.4

### Step 4.4: `cursor` submodule
Mode: Build
Outcome: 18/18 tests passing in `tests/clankmates_client/test_cursor.py`. Full non-heavy-dep regression (clankmates, json_rpc, cost_accountant, telegram core) remains green.
Contract changes: Added `src/toolkit/clankmates_client/cursor.py`, `tests/clankmates_client/test_cursor.py`, updated `__init__.py` exports.

Extracted `ThreadCursorStore` and `filter_unseen` from the atomic-write pattern in the upstream `state_store.py`. `ThreadCursorStore` maps `{thread_id: {cursor, last_message_id}}` in a JSON file, using temp-file + `os.replace` for crash safety and automatic parent-dir creation. `CursorState` is a frozen dataclass. `filter_unseen` operates on decoded messages (from `decode_clankmates_message`) keyed by `message_id`. Tests cover round-trip, restart-replay scenario (new store from same path sees prior state), atomic write (no .tmp left), nested path creation, and `filter_unseen` idempotency + order preservation.

## 2026-06-10 — Clankmates Client Step 4.5

### Step 4.5: `screen` submodule
Mode: Build
Outcome: 12/12 new tests passing in `tests/clankmates_client/test_screen.py`. Full clankmates regression: 43/43 passed. Stable-module regression (json_rpc, prompt_regression) remains green.
Contract changes: Added `src/toolkit/clankmates_client/screen.py`, `tests/clankmates_client/test_screen.py`, updated `__init__.py` exports (`ScreeningResult`, `screen_peer_message`).

Implemented `screen_peer_message` applying five sequential checks: body type, recipient (`to_player_id`), spoofing (transport sender vs body's claimed `from_player_id`), known-active-sender membership, and extra body field equality. All failures accumulate into `reasons` tuple; `accepted=True` only when reasons is empty. The message dict is expected to be a decoded message (from `decode_clankmates_message`) with `body` (dict) and `raw` sub-dict carrying a `sender` key for the Clankmates transport-level sender address. The vendor SKILL.md (lines 140-164) was inaccessible (`p:\shared` not mounted), so the implementation is derived from the spec in CLANKMATES_CLIENT_PLAN.md Phase 5 and the existing fixture/message shapes. Tests cover all five failure modes independently, an explicit spoofing case, missing sender field, non-dict body, and multi-failure accumulation.

---

## 2026-06-10 — Phase 4 Review: Clankmates Client
Phase: 4 (Review)
Mode: Build
Outcome: 43/43 clankmates tests pass. ARCH updated. State → close. Blocked for human audit.
Contract changes: Updated `ARCH_clankmates_client.md` (no source changes).

Review found no correctness or architecture violations in source code. All four submodules (subprocess, decode, cursor, screen) implement their contracts cleanly. ARCH had four documentation gaps fixed:
1. State section said "No persistent state" — wrong; cursor.py adds JSON-backed ThreadCursorStore with atomic writes. Corrected.
2. Public API section was missing cursor and screen submodule documentation. Added CursorState, ThreadCursorStore, filter_unseen, ScreeningResult, screen_peer_message with signatures.
3. Types section was missing CursorState and ScreeningResult. Added.
4. Notes section had stale "future phases" language (decode.py/cursor.py/screen.py as future work). Replaced with deferred-steps note (4.2 host ops, 4.6 governance).
Also clarified that decode functions are accessed via `toolkit.clankmates_client.decode` submodule path (not re-exported from __init__), consistent with how tests import them.

---

## 2026-06-10 — Clankmates Client Phase 4 CLOSE

**Module:** Clankmates Client | **Phase:** 4 | **Regime:** Build | **Result:** Queued steps complete; 43 tests; blocked for human audit

Phase 4 queued steps (4.1, 4.3, 4.4, 4.5) shipped and reviewed. Deferred steps (4.2 host ops, 4.6 governance) remain pending external prerequisites.

**CLOSE doc cleanup:**
- ARCHITECTURE.md row 14: "In progress" → "Complete (queued steps 4.1, 4.3, 4.4, 4.5; 43 tests; steps 4.2 and 4.6 deferred)"
- DEVPLAN Current Status: Clankmates Client row updated to reflect queued-steps completion and deferred-step status
- DEVPLAN Phase 4 Status header updated from "Active" to "Complete (queued steps)"
- Gotcha added: `p:\shared` not mounted in container — SKILL.md was inaccessible during step 4.5; spec-driven implementation used instead
- Change History row appended

**Tests at close:** 43/43 clankmates_client tests pass. Stable-module regression clean.

**Deferred work:** 4.2 (host-side ops: `post_publish`, `channel_create`, `channel_token_issue`, etc.) — queue once `p:\shared\diplomat\CLANKMATES_NOTES.md` exists from arena Phase A. 4.6 (governance + cross-consumer integration check) — queue after 4.2 ships and arena Phase C contract is firm.
