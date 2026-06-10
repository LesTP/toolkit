"""Generic Clankmates message decode helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

TIMESTAMP_FIELDS = ("created_at", "createdAt", "inserted_at", "insertedAt", "timestamp")


def decode_clankmates_message(message: dict[str, Any]) -> dict[str, Any]:
    attributes = message.get("attributes")
    raw_body = attributes.get("body") if isinstance(attributes, dict) else None
    if raw_body is None:
        raw_body = message.get("body")

    body: Any = raw_body
    if isinstance(raw_body, str):
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            body = raw_body

    return {
        "message_id": message.get("id") or message.get("message_id"),
        "thread_id": message.get("thread_id") or message.get("threadId"),
        "timestamp": message_timestamp(message),
        "body": body,
        "raw": message,
    }


def message_timestamp(message: dict[str, Any]) -> str | None:
    for field in TIMESTAMP_FIELDS:
        value = message.get(field)
        if isinstance(value, str):
            return value
    return None


def filter_by_body_type(
    messages: list[dict[str, Any]], body_type: str
) -> list[dict[str, Any]]:
    return [
        message
        for message in messages
        if isinstance(message.get("body"), dict) and message["body"].get("type") == body_type
    ]


def latest_by_timestamp(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not messages:
        return None
    return sorted(messages, key=_sort_timestamp)[-1]


def _sort_timestamp(message: dict[str, Any]) -> datetime:
    value = message.get("timestamp")
    if not isinstance(value, str):
        return datetime.min.replace(tzinfo=UTC)
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
