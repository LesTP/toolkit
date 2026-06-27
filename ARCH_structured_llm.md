# ARCH: Structured LLM

## Purpose
Reusable helpers for the common pattern:

1. Call an injected LLM client.
2. Require a plain text response.
3. Parse the response as a JSON object.
4. Validate the object against a caller-provided JSON Schema.

The module is intentionally small and domain-free. Consumers keep prompt
construction, result dataclasses, schema ownership, and domain-specific wrapper
functions.

**Provenance:** Extracted from duplicated patterns in diplomat's extraction,
analyst, adversarial, and generation modules.

## Public API

### structured_complete
- **Signature:** `async def structured_complete(llm_client: Any, config: dict[str, Any], tier: str, messages: list[dict[str, str]]) -> str`
- Low-level primitive. Calls the LLM and returns raw text. No parsing, validation, or retry.
- Kept for backwards compatibility. Prefer `structured_call` for new code.

### structured_call
- **Signature:** `async def structured_call(llm_client, config, tier, *, schema, system_prompt, user_prompt, examples=None, max_retries=1, json_mode=False, attribution=None, purpose=None) -> StructuredResult`
- **Parameters:**
  - llm_client: object exposing `complete(messages, config, tier)`
  - config: provider/client configuration dict
  - tier: model tier string (e.g. "commodity", "quality")
  - schema: JSON Schema dict to validate against
  - system_prompt: system-role instructions
  - user_prompt: user-role prompt with the actual task
  - examples: optional list of `Example` objects or `{"input": str, "output": dict}` dicts for few-shot prompting
  - max_retries: retry attempts on validation failure (default 1)
  - json_mode: opt into provider-native JSON output by annotating the config passed to the injected client with `json_mode=True` (default False)
- **Returns:** `StructuredResult` with `.success`, `.data`, `.raw`, `.retries`, `.error`
- **Behavior:**
  1. Assembles the system prompt: instructions + JSON Schema + formatted examples
  2. Calls the LLM via the injected client
  3. Parses JSON from the response
  4. Validates against the schema
  5. On parse/validation failure: appends the error to the conversation and retries
  6. On infrastructure failure (network, API error): fails immediately without retry
  7. When `json_mode=True`, passes a config copy with `json_mode=True` set; when false, leaves the caller's config untouched
- **Errors:** Does not raise. Returns `StructuredResult(success=False, error=...)` on failure.

### Example / StructuredResult (types)

```python
@dataclass
class Example:
    input: str
    output: dict[str, Any]

@dataclass
class StructuredResult:
    success: bool
    data: dict[str, Any] | None = None
    raw: str = ""
    retries: int = 0
    error: str | None = None
```

### parse_json_response
- **Signature:** `parse_json_response(response_text: str) -> dict[str, Any]`
- **Parameters:**
  - response_text: raw LLM response text expected to contain one JSON object
- **Returns:** parsed JSON object as a dict
- **Errors:** `ValueError` if the response is invalid JSON or parses to a non-object value.

Before parsing, the helper strips a single surrounding Markdown code fence
(``` ```json ... ``` `` or `` ``` ... ``` ``) when the *entire* response is wrapped in one.
This tolerates Anthropic and Google models that wrap JSON in fences even when
instructed to return raw JSON. It does not extract JSON from arbitrary prose:
responses with explanatory text outside or instead of the fence still raise.

### validate_json_schema
- **Signature:** `validate_json_schema(data: dict[str, Any], schema: dict[str, Any], label: str = "") -> None`
- **Parameters:**
  - data: parsed JSON object to validate
  - schema: JSON Schema document
  - label: optional prefix for domain-specific error messages
- **Returns:** None on success
- **Errors:** `ValueError` when validation fails.

Validation uses `jsonschema.Draft202012Validator(schema).validate(data)`.
Failure messages include the JSON path when available. If `label` is provided,
the final message is prefixed with `"{label}: "`.

Example failure format:

```text
State patch failed validation: data.promises.0.status: 'done' is not one of ['pending', 'fulfilled']
```

If the failing validator provides no path, only the schema error message is
included after the optional label.

### load_prompt
- **Signature:** `load_prompt(path: str | Path) -> str`
- **Parameters:**
  - path: text prompt file path
- **Returns:** file contents as a string
- **Errors:** filesystem exceptions propagate unchanged.

### load_schema
- **Signature:** `load_schema(path: str | Path) -> dict[str, Any]`
- **Parameters:**
  - path: JSON Schema file path
- **Returns:** parsed schema dict
- **Errors:** filesystem exceptions propagate unchanged; `ValueError` if the file is invalid JSON or parses to a non-object value.

## Dependencies

- Standard library: `inspect`, `json`, `pathlib`, `typing`
- External: `jsonschema`

No toolkit module imports are allowed. The LLM client is injected by the
consumer.

## State

No persistent state. Prompt and schema helpers read files on demand. Completion,
parsing, and validation are stateless.

## Usage Example

### structured_call (recommended)

```python
from toolkit.structured_llm import structured_call, Example

result = await structured_call(
    llm_client, config, "commodity",
    schema=load_schema("schema.json"),
    system_prompt="Extract game state as JSON.",
    user_prompt=f"Current state: {state}\n\nMessage: {text}",
    examples=[
        Example(input="Beta commits to support Alpha.", output={"promises": [...]}),
        Example(input="Round 2 begins.", output={}),
    ],
    max_retries=1,
)
if result.success:
    use(result.data)
```

### Low-level primitives

```python
from toolkit.structured_llm import (
    load_prompt,
    load_schema,
    parse_json_response,
    structured_complete,
    validate_json_schema,
)

messages = [{"role": "system", "content": load_prompt("prompt.md")}]
schema = load_schema("schema.json")

response_text = await structured_complete(llm_client, config, "commodity", messages)
data = parse_json_response(response_text)
validate_json_schema(data, schema, label="State patch failed validation")
```

Consumers then convert `data` into their own domain result types.

## Error Handling

- LLM client exceptions propagate unchanged.
- Non-string LLM responses raise `ValueError`.
- JSON parse failures raise `ValueError` with the JSON decoder detail.
- JSON values that are not objects raise `ValueError`.
- JSON Schema validation failures raise `ValueError` with optional label and
  best-effort path formatting.
- Schema files that parse to non-object JSON raise `ValueError`.

## Out of Scope

- JSON repair, partial JSON extraction, or extraction from arbitrary prose.
  (A surrounding Markdown code fence around the whole response IS stripped,
  but no other extraction is attempted.)
- LLM rate limits or provider selection.
- Importing or wrapping `toolkit.llm_client`.

## Phasing in This Pilot

### Phase 5 — JSON robustness: provider-native `json_mode` (Build)

**Goal.** Make structured calls more robust by letting them opt into
**provider-native JSON output**, instead of relying solely on prompt
instructions + the single-fence strip in `parse_json_response`. Opt-in and
default-off, so no existing caller's behavior changes.

**Module + dependency.** Module: `structured_llm`. Depends on `llm_client`
(the four providers live in `llm_client/providers.py`): Anthropic
(`messages.create`), Gemini, OpenAI (`chat.completions.create`), and
OpenRouter (⊂ OpenAI). This is a non-leaf phase — run the dependency probe
in PLAN and the integration check in CLOSE against `llm_client`.

**Scope.** Thread an opt-in `json_mode: bool` (default `False`) from
`structured_call` through `complete` / `complete_with_retry` down to each
provider. **Carry `json_mode` on the `config` passed to
`complete(messages, config, tier)` (e.g. an `LLMConfig` field), not as a new
positional/keyword argument** — the injected client signature
`complete(messages, config, tier)` is a contract every consumer implements,
so changing it would ripple across all consumers (a cross-module contract
change). Carrying it on `config` keeps that signature intact.

Per-provider behavior when `json_mode=True`:

- **OpenAI / OpenRouter:** set `response_format={"type": "json_object"}`, and
  ensure the literal word "json" appears in the prompt (an OpenAI API
  requirement for json_object mode).
- **Gemini:** set `response_mime_type="application/json"` in the generation
  config.
- **Anthropic:** no `response_format` exists — either use an assistant
  **prefill** (seed the assistant turn with `{`) or skip and leave Anthropic
  on the existing fence-stripping path. **Document the asymmetry** either way.

**Out of scope for this phase (do NOT do here):**
- Reasoning models (o1/o3, DeepSeek-R1): `response_format` does not help them.
- CoT-tolerant parsing (`<think>` stripping, balanced-`{…}` extraction) — that
  is **Change 2 / a separate later phase**, not this one. Leave
  `parse_json_response` untouched.
- Any live-key "smoke probe per provider" — those need real provider
  credentials/network and are run by the operator as a manual dependency
  probe, not by the autonomous worker. The autonomous deliverable is the
  unit-test-verifiable core below.

**Step shape (Build — smallest testable steps).** Suggested decomposition;
PLAN may refine:
1. Thread `json_mode` (default `False`) through `structured_call` →
   `config` → `complete` / `complete_with_retry`, without changing the
   injected `complete(messages, config, tier)` signature. Unit test: the flag
   reaches the provider layer when set, and the default path is unchanged.
2. OpenAI / OpenRouter provider: emit `response_format={"type":"json_object"}`
   (and ensure "json" is in the prompt) iff `json_mode`. Unit test asserts it
   is set when on and **absent** when off.
3. Gemini provider: emit `response_mime_type="application/json"` iff
   `json_mode`. Unit test asserts set-when-on / untouched-when-off.
4. Anthropic provider: implement prefill-or-skip and **document the
   asymmetry**; unit test asserts no `response_format` is sent (and the
   prefill, if implemented).
5. Docs + back-compat sweep: update this ARCH's Public API (`structured_call`
   gains `json_mode`), confirm every existing caller is unchanged (flag is
   default-off), append the Change History row.

**Acceptance.** Per-provider unit tests assert `response_format` /
`response_mime_type` is set when `json_mode=True` and untouched when off;
existing callers unchanged (default-off); the Anthropic asymmetry is
documented. (Live per-provider smoke probes are a separate manual step.)

## Escalation Triggers

Halt PLAN/EXECUTE and escalate (`EXIT 2`, devlog entry) on any of:

- **Cross-module breakage: llm_client/consumers** — if `json_mode` cannot be
  carried on `config` and would require changing the injected
  `complete(messages, config, tier)` signature in a way that breaks existing
  consumers. Surface as a contract change for decision, do not silently
  rewrite the signature.
- **Dep probe: `<provider>` contract mismatch** — if the installed provider
  SDK in `llm_client/providers.py` does not accept `response_format` /
  `response_mime_type` in the available version, so the change can't be made
  as specified.
- **Scope creep into Change 2** — if the work starts requiring changes to
  `parse_json_response` (CoT/`<think>` handling, prose extraction); that is a
  separate phase. Stop and flag rather than expanding scope.

## Change History
| Date | What Changed | Why |
|------|--------------|-----|
| 2026-06-26 | Added Phasing (Phase 5: provider-native `json_mode`, Build) + Escalation Triggers | Author the next-phase spec so autonomous PLAN can plan Change 1 without inventing scope; threads opt-in `json_mode` via `config` to four providers, default-off |
| 2026-06-27 | `structured_call` gained opt-in `json_mode` propagation on config | Preserve default-off behavior while letting callers request provider-native JSON through the injected client contract |
| 2026-05-28 | Initial ARCH - structured LLM extraction contract | Define reusable boundary before implementation |
| 2026-05-29 | `parse_json_response` strips a surrounding Markdown code fence before parsing | Anthropic and Google models wrap JSON in `` ```json ... ``` `` even when instructed to return raw JSON; without stripping, retries silently exhaust and downstream modules see nothing |
| 2026-05-28 | Added structured_call, Example, StructuredResult | High-level workflow: prompt assembly + schema injection + few-shot examples + auto-retry on validation failure |
