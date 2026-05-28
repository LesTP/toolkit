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
- **Signature:** `async def structured_call(llm_client, config, tier, *, schema, system_prompt, user_prompt, examples=None, max_retries=1) -> StructuredResult`
- **Parameters:**
  - llm_client: object exposing `complete(messages, config, tier)`
  - config: provider/client configuration dict
  - tier: model tier string (e.g. "commodity", "quality")
  - schema: JSON Schema dict to validate against
  - system_prompt: system-role instructions
  - user_prompt: user-role prompt with the actual task
  - examples: optional list of `Example` objects or `{"input": str, "output": dict}` dicts for few-shot prompting
  - max_retries: retry attempts on validation failure (default 1)
- **Returns:** `StructuredResult` with `.success`, `.data`, `.raw`, `.retries`, `.error`
- **Behavior:**
  1. Assembles the system prompt: instructions + JSON Schema + formatted examples
  2. Calls the LLM via the injected client
  3. Parses JSON from the response
  4. Validates against the schema
  5. On parse/validation failure: appends the error to the conversation and retries
  6. On infrastructure failure (network, API error): fails immediately without retry
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

The function does not extract JSON from surrounding prose. Callers that permit
markdown fences or explanatory text must normalize the response before calling
this helper.

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

- JSON repair, markdown fence stripping, or partial JSON extraction.
- LLM rate limits or provider selection.
- Importing or wrapping `toolkit.llm_client`.

## Change History
| Date | What Changed | Why |
|------|--------------|-----|
| 2026-05-28 | Initial ARCH - structured LLM extraction contract | Define reusable boundary before implementation |
| 2026-05-28 | Added structured_call, Example, StructuredResult | High-level workflow: prompt assembly + schema injection + few-shot examples + auto-retry on validation failure |
