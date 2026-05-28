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
- **Parameters:**
  - llm_client: object exposing `complete(messages, config, tier)`
  - config: provider/client configuration dict passed through unchanged
  - tier: model tier string passed through unchanged
  - messages: chat-style message dicts passed through unchanged
- **Returns:** plain string response from the LLM client
- **Errors:** `ValueError` if the client response is not a plain string.

`llm_client.complete(...)` may return either a string directly or an awaitable
that resolves to a string. `structured_complete` handles both forms.

The LLM client protocol intentionally matches `toolkit.llm_client.complete`:
`complete(messages, config, tier)`. Structured LLM does not import
`toolkit.llm_client`; consumers pass the client/config they want.

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

- Prompt construction and message templates.
- Domain-specific result dataclasses.
- JSON repair, markdown fence stripping, or partial JSON extraction.
- LLM retries, rate limits, accounting, or provider selection.
- Importing or wrapping `toolkit.llm_client`.

## Change History
| Date | What Changed | Why |
|------|--------------|-----|
| 2026-05-28 | Initial ARCH - structured LLM extraction contract | Define reusable boundary before implementation |
