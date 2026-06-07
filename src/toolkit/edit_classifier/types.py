from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class EditClassification:
    category: str
    confidence: float
    rationale: str
    classifier_model: str
    classified_at: datetime

    def __post_init__(self) -> None:
        if self.classified_at.tzinfo is None:
            object.__setattr__(
                self, "classified_at", self.classified_at.replace(tzinfo=timezone.utc)
            )
