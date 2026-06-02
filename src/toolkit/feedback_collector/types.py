"""Dataclasses for the Feedback Collector public API.

The Feedback Collector writes feedback events as memory notes via a
caller-supplied memory store. To stay decoupled from any specific memory
implementation, it constructs notes and patches with the internal
``_NoteInput`` / ``_NotePatch`` dataclasses below. These are structurally
compatible with Phosphene's ``NoteInput`` / ``NotePatch`` (same field names
and types), so any memory store that accepts those by duck-typing will
accept these too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


def _require_positive_timedelta(value: timedelta, field_name: str) -> None:
    if not isinstance(value, timedelta):
        raise ValueError(f"{field_name} must be a timedelta")
    if value <= timedelta(0):
        raise ValueError(f"{field_name} must be positive")


def _require_string_list(value: list[str], field_name: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{field_name} must contain non-empty strings")


@dataclass
class FeedbackEvent:
    output_message_id: str
    output_intent_tag: str
    output_mode: str
    signal_type: str
    signal_value: str | None = None
    source_note_ids: list[str] = field(default_factory=list)
    retention_criteria: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class FeedbackCollectorConfig:
    silence_window: timedelta = timedelta(hours=24)
    delayed_recheck_window: timedelta = timedelta(days=7)
    positive_reactions: list[str] = field(
        default_factory=lambda: ["👍", "❤️", "🔥", "💡", "🤔"]
    )
    negative_reactions: list[str] = field(default_factory=lambda: ["👎"])
    reply_is_positive: bool = True
    forward_is_positive: bool = True

    def __post_init__(self) -> None:
        _require_positive_timedelta(self.silence_window, "silence_window")
        _require_positive_timedelta(
            self.delayed_recheck_window,
            "delayed_recheck_window",
        )
        _require_string_list(self.positive_reactions, "positive_reactions")
        _require_string_list(self.negative_reactions, "negative_reactions")
        if not isinstance(self.reply_is_positive, bool):
            raise ValueError("reply_is_positive must be a bool")
        if not isinstance(self.forward_is_positive, bool):
            raise ValueError("forward_is_positive must be a bool")


@dataclass
class OutputRecord:
    message_id: str
    intent_tag: str
    output_mode: str
    source_note_ids: list[str]
    retention_criteria: list[str]
    delivered_at: datetime
    feedback_events: list[FeedbackEvent] = field(default_factory=list)
    silence_recorded: bool = False


@dataclass
class _NoteInput:
    """Internal note shape used to write feedback notes via the memory writer.

    Field names and types mirror Phosphene's ``memory_store.NoteInput`` so any
    duck-typed write API (``store_note(note)`` reading attributes) accepts it.
    Not part of the public surface — consumers see only ``FeedbackEvent``.
    """

    tier: int
    content: str
    title: str
    importance: float = 0.0
    unresolvedness: float = 0.0
    links: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source: str | None = None
    friction_target: str | None = None
    embedding: Any = None
    attractor_relevance: float | None = None
    cluster_group: str | None = None
    created_at: datetime | None = None


@dataclass
class _NotePatch:
    """Internal patch shape used to bump unresolvedness on a source note.

    Field names mirror Phosphene's ``memory_store.NotePatch``. All fields
    default to ``None`` so the patch only mutates what the collector sets.
    """

    content: str | None = None
    title: str | None = None
    importance: float | None = None
    unresolvedness: float | None = None
    links: list[str] | None = None
    tags: list[str] | None = None
    embedding: Any = None
    attractor_relevance: float | None = None
