import json
from pathlib import Path

from toolkit.clankmates_client.decode import (
    decode_clankmates_message,
    filter_by_body_type,
    latest_by_timestamp,
    message_timestamp,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_decode_message_body_json_string_from_attributes():
    message = {"id": "m1", "attributes": {"body": '{"type":"setup_report","game_id":"g"}'}}

    decoded = decode_clankmates_message(message)

    assert decoded["message_id"] == "m1"
    assert decoded["body"] == {"type": "setup_report", "game_id": "g"}
    assert decoded["raw"] == message


def test_decode_message_body_leaves_plain_text_body_unparsed():
    message = {"id": "m2", "body": "plain text"}

    decoded = decode_clankmates_message(message)

    assert decoded["body"] == "plain text"


def test_message_timestamp_prefers_known_fields():
    assert message_timestamp({"created_at": "2026-06-07T10:00:00Z"}) == "2026-06-07T10:00:00Z"
    assert message_timestamp({"createdAt": "2026-06-07T10:00:00Z"}) == "2026-06-07T10:00:00Z"
    assert message_timestamp({"inserted_at": "2026-06-07T10:00:00Z"}) == "2026-06-07T10:00:00Z"
    assert message_timestamp({"insertedAt": "2026-06-07T10:00:00Z"}) == "2026-06-07T10:00:00Z"
    assert message_timestamp({"timestamp": "2026-06-07T10:00:00Z"}) == "2026-06-07T10:00:00Z"
    assert message_timestamp({"created_at": 1}) is None


def test_filter_by_body_type_returns_matching_decoded_messages():
    page = json.loads((FIXTURES / "inbox_page_phase_reports.json").read_text())
    decoded = [decode_clankmates_message(message) for message in page["messages"]]

    selected = filter_by_body_type(decoded, "movement_phase_report")

    assert [message["message_id"] for message in selected] == ["m-other", "m-new"]


def test_latest_by_timestamp_returns_newest_message():
    page = json.loads((FIXTURES / "inbox_page_phase_reports.json").read_text())
    decoded = [decode_clankmates_message(message) for message in page["messages"]]

    latest = latest_by_timestamp(decoded)

    assert latest is not None
    assert latest["message_id"] == "m-new"


def test_latest_by_timestamp_returns_none_for_empty_input():
    assert latest_by_timestamp([]) is None


def test_filter_by_body_type_handles_diplomacy_page():
    page = json.loads((FIXTURES / "inbox_page_diplomacy.json").read_text())
    decoded = [decode_clankmates_message(message) for message in page["messages"]]

    selected = filter_by_body_type(decoded, "diplomacy_message")

    assert [message["body"]["body"] for message in selected[-3:]] == [
        "message 11",
        "message 12",
        "message 13",
    ]
