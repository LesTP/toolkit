from __future__ import annotations

from datetime import timezone
import json

import pytest

from toolkit.edit_classifier import (
    EDIT_CLASSIFICATION_SCHEMA,
    EditClassification,
    LLMEditClassifier,
)


class FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.mark.asyncio
async def test_classify_returns_structured_classification(tmp_path):
    prompt_path = tmp_path / "edit_classifier.txt"
    prompt_path.write_text("Edit classifier prompt.", encoding="utf-8")

    client = FakeLLMClient(
        json.dumps(
            {
                "category": "tone_softer",
                "confidence": 0.91,
                "rationale": "The edit removes confrontational phrasing.",
            }
        )
    )
    classifier = LLMEditClassifier(
        client,
        llm_config={"provider": "google", "models": {"commodity": "gemini-2.5-flash-lite"}},
        tier="commodity",
        prompt_path=prompt_path,
    )

    result = await classifier.classify(
        original="We will crush your proposal.",
        edited="We can push back on your proposal.",
        edit_notes="Soften tone.",
    )

    assert result == EditClassification(
        category="tone_softer",
        confidence=0.91,
        rationale="The edit removes confrontational phrasing.",
        classifier_model="gemini-2.5-flash-lite",
        classified_at=result.classified_at,
    )
    assert result.classified_at.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_classify_forwards_prompt_and_metadata(tmp_path):
    prompt_path = tmp_path / "edit_classifier.txt"
    prompt_path.write_text("Edit classifier prompt.", encoding="utf-8")

    client = FakeLLMClient(
        json.dumps(
            {
                "category": "commitment_removed",
                "confidence": 0.8,
                "rationale": "The edit removed a concrete promise.",
            }
        )
    )
    classifier = LLMEditClassifier(
        client,
        llm_config={"provider": "openai", "models": {"commodity": "gpt-4.1-mini"}},
        tier="commodity",
        prompt_path=prompt_path,
    )

    await classifier.classify(
        original="We will support Belgium and send 3 units.",
        edited="We will support Belgium.",
        edit_notes=None,
    )

    call = client.calls[0]
    assert call["purpose"] == "edit_classification"
    assert call["attribution"] is None
    assert call["tier"] == "commodity"
    assert call["messages"][0]["role"] == "system"
    assert "Edit classifier prompt." in call["messages"][0]["content"]
    assert "We will support Belgium and send 3 units." in call["messages"][1]["content"]
    assert "We will support Belgium." in call["messages"][1]["content"]
    assert "[none]" in call["messages"][1]["content"]


@pytest.mark.asyncio
async def test_classify_rejects_blank_inputs(tmp_path):
    prompt_path = tmp_path / "edit_classifier.txt"
    prompt_path.write_text("Edit classifier prompt.", encoding="utf-8")
    classifier = LLMEditClassifier(
        FakeLLMClient("{}"),
        llm_config={},
        tier="commodity",
        prompt_path=prompt_path,
    )

    with pytest.raises(ValueError, match="original must not be blank"):
        await classifier.classify("   ", "Edited", None)

    with pytest.raises(ValueError, match="edited must not be blank"):
        await classifier.classify("Original", "   ", None)


@pytest.mark.asyncio
async def test_classify_raises_on_invalid_category(tmp_path):
    prompt_path = tmp_path / "edit_classifier.txt"
    prompt_path.write_text("Edit classifier prompt.", encoding="utf-8")
    client = FakeLLMClient(
        json.dumps(
            {
                "category": "unknown",
                "confidence": 0.5,
                "rationale": "Invalid category.",
            }
        )
    )
    classifier = LLMEditClassifier(client, llm_config={}, tier="commodity", prompt_path=prompt_path)

    with pytest.raises(RuntimeError, match="unknown"):
        await classifier.classify("Original", "Edited", None)


def test_schema_constrains_categories_and_confidence():
    assert EDIT_CLASSIFICATION_SCHEMA["properties"]["category"]["enum"] == [
        "tone_softer",
        "tone_harder",
        "commitment_removed",
        "ambiguity_added",
        "constraint_enforcement",
        "persona_correction",
    ]
    assert EDIT_CLASSIFICATION_SCHEMA["properties"]["confidence"]["minimum"] == 0
    assert EDIT_CLASSIFICATION_SCHEMA["properties"]["confidence"]["maximum"] == 1
