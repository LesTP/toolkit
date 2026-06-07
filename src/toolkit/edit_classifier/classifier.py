from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toolkit.structured_llm import structured_call

from toolkit.edit_classifier.types import EditClassification


EDIT_CLASSIFICATION_CATEGORIES = (
    "tone_softer",
    "tone_harder",
    "commitment_removed",
    "ambiguity_added",
    "constraint_enforcement",
    "persona_correction",
)

EDIT_CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["category", "confidence", "rationale"],
    "properties": {
        "category": {"type": "string", "enum": list(EDIT_CLASSIFICATION_CATEGORIES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string", "minLength": 1},
    },
}


class LLMEditClassifier:
    """LLM-as-judge categorical classifier for review-gate edit logs.

    Consumers wire this through a project-side ``build_*`` factory that
    translates the project's own config shape into the constructor kwargs
    expected here. The classifier itself is config-agnostic.
    """

    def __init__(
        self,
        llm_client: Any,
        llm_config: Any,
        tier: Any,
        prompt_path: str | Path,
        attribution: str | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.llm_config = llm_config
        self.tier = tier
        self.system_prompt = Path(prompt_path).read_text(encoding="utf-8").strip()
        self.classifier_model = _resolve_classifier_model(llm_config, tier)
        self.attribution = attribution

    async def classify(
        self,
        original: str,
        edited: str,
        edit_notes: str | None,
    ) -> EditClassification:
        if not original.strip():
            raise ValueError("original must not be blank")
        if not edited.strip():
            raise ValueError("edited must not be blank")

        user_prompt = _build_user_prompt(original, edited, edit_notes)

        result = await structured_call(
            self.llm_client,
            self.llm_config,
            self.tier,
            schema=EDIT_CLASSIFICATION_SCHEMA,
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            max_retries=1,
            purpose="edit_classification",
            attribution=self.attribution,
        )

        if not result.success:
            raise RuntimeError(result.error or "Edit classification failed")

        data = result.data or {}
        category = data.get("category", "")
        confidence = data.get("confidence", 0.0)
        rationale = data.get("rationale", "")

        if category not in EDIT_CLASSIFICATION_CATEGORIES:
            raise ValueError(f"Invalid edit classification category: {category}")
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            raise ValueError("Edit classification confidence must be between 0 and 1")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("Edit classification rationale must not be blank")

        return EditClassification(
            category=category,
            confidence=float(confidence),
            rationale=rationale.strip(),
            classifier_model=self.classifier_model,
            classified_at=datetime.now(timezone.utc),
        )


def _build_user_prompt(original: str, edited: str, edit_notes: str | None) -> str:
    notes = edit_notes.strip() if isinstance(edit_notes, str) and edit_notes.strip() else "[none]"
    return "\n\n".join(
        [
            "Classify the edit into exactly one category.",
            "Original draft:",
            original.strip(),
            "Edited draft:",
            edited.strip(),
            "Edit notes:",
            notes,
            "Return the category, confidence, and a short rationale.",
        ]
    )


def _resolve_classifier_model(llm_config: Any, tier: Any) -> str:
    models = llm_config.get("models", {}) if isinstance(llm_config, dict) else {}
    if isinstance(models, dict):
        model = models.get(tier)
        if isinstance(model, str) and model.strip():
            return model.strip()
        if isinstance(tier, str) and tier.strip():
            return tier.strip()
    return "unknown"


__all__ = [
    "EDIT_CLASSIFICATION_SCHEMA",
    "EDIT_CLASSIFICATION_CATEGORIES",
    "LLMEditClassifier",
]
