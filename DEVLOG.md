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
