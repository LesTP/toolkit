"""Peer-DM screening rules for Clankmates messages.

SOURCE: adapted from clanker-courts-player-client/skills/clanker-courts-operator/SKILL.md:140-164
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScreeningResult:
    accepted: bool
    reasons: tuple[str, ...]


def screen_peer_message(
    message: dict[str, Any],
    *,
    expected_to: str,
    expected_body_type: str,
    expected_extra_fields: dict[str, str] | None = None,
    known_active_senders: set[str],
) -> ScreeningResult:
    """Apply standard peer-DM screening checks against a decoded message.

    message must be a decoded message (output of decode_clankmates_message).
    The raw sub-dict must carry a 'sender' key with the Clankmates address of
    the transport-level sender.

    Checks applied in order:
    - body type matches expected_body_type
    - to_player_id matches expected_to
    - transport sender matches body's claimed from_player_id (spoofing guard)
    - sender is in known_active_senders
    - each key/value in expected_extra_fields matches the decoded body
    """
    reasons: list[str] = []
    body = message.get("body")
    raw = message.get("raw") or {}
    sender: str | None = raw.get("sender")
    body_dict: dict[str, Any] = body if isinstance(body, dict) else {}

    actual_type = body_dict.get("type")
    if actual_type != expected_body_type:
        reasons.append(f"body type {actual_type!r} != expected {expected_body_type!r}")

    actual_to = body_dict.get("to_player_id")
    if actual_to != expected_to:
        reasons.append(f"to_player_id {actual_to!r} != expected {expected_to!r}")

    claimed_from = body_dict.get("from_player_id")
    if sender != claimed_from:
        reasons.append(f"sender {sender!r} != body from_player_id {claimed_from!r}")

    if sender not in known_active_senders:
        reasons.append(f"sender {sender!r} not in known_active_senders")

    if expected_extra_fields:
        for field, expected_value in expected_extra_fields.items():
            actual_value = body_dict.get(field)
            if actual_value != expected_value:
                reasons.append(
                    f"body field {field!r}: {actual_value!r} != {expected_value!r}"
                )

    return ScreeningResult(accepted=not reasons, reasons=tuple(reasons))
