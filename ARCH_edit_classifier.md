# ARCH: Edit Classifier

## Purpose

LLM-as-judge categorical classifier for review-gate edit logs. Takes an
`(original_draft, edited_draft, optional_edit_notes)` triple and returns a
typed `EditClassification` with a category (one of six fixed values), a
confidence in `[0, 1]`, and a one-line rationale.

The intended use is a coached-review feedback loop: an operator edits a
draft, the classifier categorises the edit, and the consumer surfaces
recurring patterns (e.g. "operator removes commitments often") so the
underlying prompt can be tightened.

**Provenance:** Extracted from Diplomat's `modules/edit_classifier` in 2026-06-07.
Second-consumer rule satisfied by Clanker Courts (incoming).

## Public API

### LLMEditClassifier

```python
class LLMEditClassifier:
    def __init__(
        self,
        llm_client: Any,
        llm_config: Any,
        tier: Any,
        prompt_path: str | Path,
        attribution: str | None = None,
    ) -> None

    async def classify(
        self,
        original: str,
        edited: str,
        edit_notes: str | None,
    ) -> EditClassification
```

- `__init__(...)` — loads the prompt file from disk (raises if missing),
  resolves the classifier model name from `llm_config["models"][tier]` for
  attribution into the returned `EditClassification.classifier_model`.
- `classify(original, edited, edit_notes)` — validates inputs are
  non-blank, calls `toolkit.structured_llm.structured_call` with the fixed
  `EDIT_CLASSIFICATION_SCHEMA`, validates the returned category is one of
  `EDIT_CLASSIFICATION_CATEGORIES`, returns an `EditClassification` with
  `classified_at` set to UTC `datetime.now`.

The classifier is config-agnostic. Consumers wire it through a
project-side `build_*` factory that translates the project's config shape
(e.g. Diplomat's `pipeline.yaml` `{"primary": {...}}` convention) into the
`llm_config` / `tier` / `prompt_path` triple this constructor expects. See
Consumer notes below.

### Constants

```python
EDIT_CLASSIFICATION_CATEGORIES = (
    "tone_softer",
    "tone_harder",
    "commitment_removed",
    "ambiguity_added",
    "constraint_enforcement",
    "persona_correction",
)

EDIT_CLASSIFICATION_SCHEMA: dict[str, Any]  # JSON schema for structured_call
```

The categories are deliberately hardcoded for the v1 surface. Both
Diplomat and Clanker Courts use the same six (five translate verbatim;
`constraint_enforcement` covers rule-breaking content in both domains).
Parameterise the category list only when a third consumer needs a
different one.

## Types

```python
@dataclass(frozen=True)
class EditClassification:
    category: str            # one of EDIT_CLASSIFICATION_CATEGORIES
    confidence: float        # in [0, 1]
    rationale: str           # one-line explanation, non-blank
    classifier_model: str    # model name used for the call (audit trail)
    classified_at: datetime  # tz-aware UTC; naive datetimes are upgraded
```

`classified_at` is normalised to UTC in `__post_init__`; passing a naive
`datetime` is accepted and upgraded with `tzinfo=timezone.utc`.

## Schema

The fixed JSON schema enforced on the LLM response:

```python
{
    "type": "object",
    "additionalProperties": False,
    "required": ["category", "confidence", "rationale"],
    "properties": {
        "category": {"type": "string", "enum": [...six categories...]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string", "minLength": 1},
    },
}
```

`structured_call` retries on schema-validation failure (current
`max_retries=1`); a final failure raises `RuntimeError`. Out-of-enum
categories, out-of-range confidence, and empty rationale all raise
`ValueError` from `classify()` itself as a defensive second check.

## Inputs

- `original`, `edited` — non-blank strings (whitespace-only is rejected).
- `edit_notes` — optional free-form operator notes; `None` or blank
  renders as `[none]` in the user prompt.

## Outputs

- `EditClassification` per `classify()` call.

Consumer is responsible for storing the result; this module performs no
I/O beyond the LLM call and the prompt-file read at construction.

## State

None. `LLMEditClassifier` holds its `system_prompt` and configured model
name at construction but performs no mutation across calls.

## Usage Example

```python
from pathlib import Path

from toolkit.edit_classifier import LLMEditClassifier, EditClassification


# Consumer wires its own llm_client + config translation.
classifier = LLMEditClassifier(
    llm_client=my_llm_client,                  # any object with .complete(**kwargs)
    llm_config={
        "provider": "openai",
        "models": {"commodity": "gpt-4.1-mini"},
        "api_key": "...",
    },
    tier="commodity",
    prompt_path=Path("config/prompts/edit_classifier.txt"),
    attribution="alpha",                        # optional, threaded into cost ledger
)

result: EditClassification = await classifier.classify(
    original="We will crush your proposal.",
    edited="We can push back on your proposal.",
    edit_notes="Soften tone.",
)

# result.category    -> "tone_softer"
# result.confidence  -> 0.9 (or whatever the model returned, validated in [0,1])
# result.rationale   -> "The edit removes confrontational phrasing." (model-generated)
# result.classifier_model -> "gpt-4.1-mini"
# result.classified_at    -> datetime.now(timezone.utc) at the moment of the call
```

## Errors

- `ValueError` on blank `original` or `edited`.
- `ValueError` if the LLM returns an out-of-enum category, an out-of-range
  confidence, or a blank rationale (defensive — schema should already
  prevent these via `structured_call`).
- `RuntimeError` if `structured_call` exhausts retries.
- `FileNotFoundError` (from `Path.read_text`) if `prompt_path` does not
  exist at construction time.

## Dependencies

- `toolkit.structured_llm` for the schema-enforced LLM call.
- Caller supplies the LLM client (any object exposing
  `await complete(**kwargs)`); toolkit's `llm_client` is the obvious
  choice but not required.
- Standard library only otherwise (`dataclasses`, `datetime`, `pathlib`).

## Consumer notes

Consumers typically:

1. Write a project-local prompt file at a path of their choice (the
   Diplomat-bundled prompt in `config/prompts/edit_classifier.txt` is a
   reasonable starting point; tweak phrasing for the consumer's domain).
2. Write a project-side `build_edit_classifier(...)` factory that knows
   the consumer's own config-file shape and translates it into the
   `llm_config` / `tier` / `prompt_path` triple. Mirror the
   `build_reconciler` pattern in Diplomat's `modules/reconciliation`.
3. Persist `EditClassification` rows in their own store (Diplomat uses an
   `edit_classifications` SQLite table FK'd to its `review_gate_edits`
   table; the persistence schema is a consumer concern, not toolkit's).
4. Surface recurring patterns to the operator (e.g. via a
   `/edits-summary` command) so prompt refinement closes the loop.

The classifier itself is intentionally domain-free. Operational policy —
when to classify, how to display patterns, when a pattern crosses the
threshold for a prompt update — lives in the consumer.
