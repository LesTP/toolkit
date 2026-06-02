"""Feedback Collector public constructor and ARCH method shell.

The ``FeedbackCollector`` writes feedback events as memory notes via a
caller-supplied memory store. The memory store must structurally support:

* ``get_note(note_id)`` returning an object with ``.tags``, ``.tier``,
  ``.unresolvedness`` attributes
* ``store_note(note)`` accepting any object with the same field shape as
  ``_NoteInput`` (see ``types.py``)
* ``update_note(note_id, patch)`` accepting any object with the same field
  shape as ``_NotePatch``

Phosphene's ``memory_store.MemoryStore`` satisfies this contract.
"""

from __future__ import annotations

from datetime import datetime, timezone

from toolkit.feedback_collector.types import (
    FeedbackCollectorConfig,
    FeedbackEvent,
    OutputRecord,
    _NoteInput as NoteInput,
    _NotePatch as NotePatch,
)

_RETENTION_CRITERIA_TAGS = {
    "precision_surplus",
    "liminality",
    "friction",
    "unexpected_connection",
    "structural_insight",
    "link_density",
    "cluster_novelty",
    "unresolvedness_affinity",
    "wild_card",
}


class FeedbackCollector:
    """Track delivered outputs and normalize feedback into Memory Store events."""

    def __init__(
        self,
        memory_store,
        config: FeedbackCollectorConfig | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.config = config or FeedbackCollectorConfig()
        self.output_records: dict[str, OutputRecord] = {}

    def register_output(self, output, delivery) -> None:
        if not delivery.success or delivery.message_id is None:
            return None

        source_note_ids = list(output.source_note_ids)
        self.output_records[delivery.message_id] = OutputRecord(
            message_id=delivery.message_id,
            intent_tag=output.intent_tag,
            output_mode=output.output_mode,
            source_note_ids=source_note_ids,
            retention_criteria=self._retention_criteria_for_source_notes(
                source_note_ids
            ),
            delivered_at=datetime.now(timezone.utc),
        )
        return None

    def _retention_criteria_for_source_notes(
        self, source_note_ids: list[str]
    ) -> list[str]:
        criteria: list[str] = []
        seen: set[str] = set()
        for note_id in source_note_ids:
            try:
                note = self.memory_store.get_note(note_id)
            except Exception:
                continue
            for tag in getattr(note, "tags", []):
                if tag not in _RETENTION_CRITERIA_TAGS or tag in seen:
                    continue
                seen.add(tag)
                criteria.append(tag)
        return criteria

    def process_signal(self, signal) -> FeedbackEvent | None:
        record = self.output_records.get(signal.message_id)
        if record is None:
            return None

        signal_type = self._classify_signal(signal)
        if signal_type is None:
            return None

        event = FeedbackEvent(
            output_message_id=record.message_id,
            output_intent_tag=record.intent_tag,
            output_mode=record.output_mode,
            signal_type=signal_type,
            signal_value=signal.value,
            source_note_ids=list(record.source_note_ids),
            retention_criteria=list(record.retention_criteria),
            timestamp=signal.timestamp,
        )
        self.memory_store.store_note(_feedback_note_input(event))
        record.feedback_events.append(event)
        if self._is_positive_event(event):
            self.update_unresolvedness_on_feedback(event)
        return event

    def _classify_signal(self, signal) -> str | None:
        signal_type = signal.signal_type
        if signal_type == "reaction":
            values = _reaction_values(signal.value)
            if any(value in self.config.positive_reactions for value in values):
                return "like"
            if any(value in self.config.negative_reactions for value in values):
                return "dislike"
            return None
        if signal_type == "reply":
            return "reply"
        if signal_type == "forward":
            return "forward"
        return None

    def check_silence(self) -> list[FeedbackEvent]:
        now = datetime.now(timezone.utc)
        events: list[FeedbackEvent] = []

        for record in list(self.output_records.values()):
            if (
                record.silence_recorded
                or record.feedback_events
                or now < record.delivered_at + self.config.silence_window
            ):
                continue

            event = FeedbackEvent(
                output_message_id=record.message_id,
                output_intent_tag=record.intent_tag,
                output_mode=record.output_mode,
                signal_type="silence",
                source_note_ids=list(record.source_note_ids),
                retention_criteria=list(record.retention_criteria),
                timestamp=now,
            )
            self.memory_store.store_note(_feedback_note_input(event))
            record.feedback_events.append(event)
            record.silence_recorded = True
            events.append(event)

        self._prune_old_records(now)
        return events

    def check_delayed_engagement(self) -> list[FeedbackEvent]:
        return []

    def update_unresolvedness_on_feedback(self, event: FeedbackEvent) -> None:
        for note_id in event.source_note_ids:
            try:
                note = self.memory_store.get_note(note_id)
            except Exception:
                continue

            if getattr(note, "tier", None) != 1:
                continue

            current = float(getattr(note, "unresolvedness", 0.0))
            self.memory_store.update_note(
                note_id,
                NotePatch(unresolvedness=min(1.0, current + 0.1)),
            )
        return None

    def _is_positive_event(self, event: FeedbackEvent) -> bool:
        if event.signal_type == "like":
            return True
        if event.signal_type == "reply":
            return self.config.reply_is_positive
        if event.signal_type == "forward":
            return self.config.forward_is_positive
        return False

    def _prune_old_records(self, now: datetime) -> None:
        cutoff = now - (self.config.silence_window * 2)
        for message_id, record in list(self.output_records.items()):
            if record.delivered_at < cutoff:
                del self.output_records[message_id]


def _reaction_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _feedback_note_input(event: FeedbackEvent) -> NoteInput:
    return NoteInput(
        tier=1,
        content=f"Feedback: {event.signal_type} on [{event.output_intent_tag}] output",
        title=f"Feedback: {event.signal_type} on {event.output_intent_tag}",
        importance=_importance_from_signal(event),
        tags=["feedback", event.signal_type, event.output_intent_tag]
        + list(event.retention_criteria),
        source="feedback",
        links=list(event.source_note_ids),
    )


def _importance_from_signal(event: FeedbackEvent) -> float:
    if event.signal_type == "forward":
        return 0.9
    if event.signal_type == "reply":
        return 0.7
    if event.signal_type == "dislike":
        return 0.8
    if event.signal_type == "silence":
        return 0.3
    if event.signal_type == "delayed_positive":
        return 0.85
    if event.signal_type == "like":
        if event.signal_value in {"💡", "🤔"}:
            return 0.7
        return 0.6
    return 0.0
