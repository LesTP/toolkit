"""Tests for clankmates_client.screen — peer-DM screening rules."""

from __future__ import annotations

import pytest

from toolkit.clankmates_client.screen import ScreeningResult, screen_peer_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(
    *,
    sender: str | None,
    body_type: str = "diplomacy_message",
    from_player_id: str = "red",
    to_player_id: str = "blue",
    game_id: str = "demo",
    extra_body: dict | None = None,
) -> dict:
    """Build a decoded message in the shape returned by decode_clankmates_message."""
    body: dict = {
        "type": body_type,
        "from_player_id": from_player_id,
        "to_player_id": to_player_id,
        "game_id": game_id,
        "body": "Let us negotiate.",
    }
    if extra_body:
        body.update(extra_body)
    raw: dict = {"id": "m1", "thread_id": "t1"}
    if sender is not None:
        raw["sender"] = sender
    return {
        "message_id": "m1",
        "thread_id": "t1",
        "timestamp": None,
        "body": body,
        "raw": raw,
    }


_KNOWN_SENDERS: set[str] = {"red", "green", "yellow"}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_accepted_when_all_checks_pass():
    msg = _make_message(sender="red")
    result = screen_peer_message(
        msg,
        expected_to="blue",
        expected_body_type="diplomacy_message",
        expected_extra_fields={"game_id": "demo"},
        known_active_senders=_KNOWN_SENDERS,
    )
    assert result == ScreeningResult(accepted=True, reasons=())


def test_accepted_without_extra_fields():
    msg = _make_message(sender="red")
    result = screen_peer_message(
        msg,
        expected_to="blue",
        expected_body_type="diplomacy_message",
        known_active_senders=_KNOWN_SENDERS,
    )
    assert result.accepted is True
    assert result.reasons == ()


# ---------------------------------------------------------------------------
# Body type failure
# ---------------------------------------------------------------------------


def test_rejected_on_wrong_body_type():
    msg = _make_message(sender="red", body_type="setup_report")
    result = screen_peer_message(
        msg,
        expected_to="blue",
        expected_body_type="diplomacy_message",
        known_active_senders=_KNOWN_SENDERS,
    )
    assert result.accepted is False
    assert any("body type" in r for r in result.reasons)


def test_rejected_on_non_dict_body():
    decoded = {
        "message_id": "m1",
        "thread_id": "t1",
        "timestamp": None,
        "body": "plain text",
        "raw": {"id": "m1", "sender": "red"},
    }
    result = screen_peer_message(
        decoded,
        expected_to="blue",
        expected_body_type="diplomacy_message",
        known_active_senders=_KNOWN_SENDERS,
    )
    assert result.accepted is False


# ---------------------------------------------------------------------------
# Recipient failure
# ---------------------------------------------------------------------------


def test_rejected_on_wrong_recipient():
    msg = _make_message(sender="red", to_player_id="green")
    result = screen_peer_message(
        msg,
        expected_to="blue",
        expected_body_type="diplomacy_message",
        known_active_senders=_KNOWN_SENDERS,
    )
    assert result.accepted is False
    assert any("to_player_id" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Spoofing failure (explicit test)
# ---------------------------------------------------------------------------


def test_rejected_on_spoofed_sender():
    """Transport sender is 'green' but body claims from_player_id 'red'."""
    msg = _make_message(sender="green", from_player_id="red")
    result = screen_peer_message(
        msg,
        expected_to="blue",
        expected_body_type="diplomacy_message",
        known_active_senders=_KNOWN_SENDERS,
    )
    assert result.accepted is False
    assert any("sender" in r and "from_player_id" in r for r in result.reasons)


def test_rejected_on_missing_sender_field():
    """No sender field in raw message → fails spoofing + known-senders checks."""
    msg = _make_message(sender=None)
    result = screen_peer_message(
        msg,
        expected_to="blue",
        expected_body_type="diplomacy_message",
        known_active_senders=_KNOWN_SENDERS,
    )
    assert result.accepted is False
    assert len(result.reasons) >= 2


# ---------------------------------------------------------------------------
# Known-active-sender failure
# ---------------------------------------------------------------------------


def test_rejected_on_unknown_sender():
    msg = _make_message(sender="unknown_player")
    result = screen_peer_message(
        msg,
        expected_to="blue",
        expected_body_type="diplomacy_message",
        known_active_senders=_KNOWN_SENDERS,
    )
    assert result.accepted is False
    assert any("not in known_active_senders" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Extra body field failure
# ---------------------------------------------------------------------------


def test_rejected_on_wrong_game_id():
    msg = _make_message(sender="red", game_id="other_game")
    result = screen_peer_message(
        msg,
        expected_to="blue",
        expected_body_type="diplomacy_message",
        expected_extra_fields={"game_id": "demo"},
        known_active_senders=_KNOWN_SENDERS,
    )
    assert result.accepted is False
    assert any("game_id" in r for r in result.reasons)


def test_rejected_on_wrong_extra_field_value():
    msg = _make_message(sender="red")
    result = screen_peer_message(
        msg,
        expected_to="blue",
        expected_body_type="diplomacy_message",
        expected_extra_fields={"game_id": "demo", "phase": "retreat"},
        known_active_senders=_KNOWN_SENDERS,
    )
    assert result.accepted is False
    assert any("phase" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Multiple failures accumulate
# ---------------------------------------------------------------------------


def test_multiple_failures_all_appear_in_reasons():
    """Wrong type + wrong recipient + spoofing → all three reasons reported."""
    msg = _make_message(
        sender="green",
        body_type="setup_report",
        from_player_id="red",
        to_player_id="yellow",
    )
    result = screen_peer_message(
        msg,
        expected_to="blue",
        expected_body_type="diplomacy_message",
        expected_extra_fields={"game_id": "other"},
        known_active_senders=_KNOWN_SENDERS,
    )
    assert result.accepted is False
    assert len(result.reasons) >= 3


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------


def test_screening_result_is_frozen():
    r = ScreeningResult(accepted=True, reasons=())
    with pytest.raises((AttributeError, TypeError)):
        r.accepted = False  # type: ignore[misc]
