"""Tests for clankmates_client.cursor — ThreadCursorStore and filter_unseen."""

from __future__ import annotations

import json

import pytest

from toolkit.clankmates_client.cursor import (
    CursorState,
    ThreadCursorStore,
    filter_unseen,
)


# ---------------------------------------------------------------------------
# ThreadCursorStore — basic round-trip
# ---------------------------------------------------------------------------


def test_get_returns_none_for_unknown_thread(tmp_path):
    store = ThreadCursorStore(tmp_path / "cursors.json")
    assert store.get("thread-abc") is None


def test_advance_and_get_round_trip(tmp_path):
    store = ThreadCursorStore(tmp_path / "cursors.json")
    store.advance("t1", cursor="cur-100", last_message_id="msg-1")

    result = store.get("t1")
    assert result == CursorState(cursor="cur-100", last_message_id="msg-1")


def test_advance_overwrites_previous_entry(tmp_path):
    store = ThreadCursorStore(tmp_path / "cursors.json")
    store.advance("t1", cursor="cur-100", last_message_id="msg-1")
    store.advance("t1", cursor="cur-200", last_message_id="msg-2")

    result = store.get("t1")
    assert result == CursorState(cursor="cur-200", last_message_id="msg-2")


def test_multiple_threads_stored_independently(tmp_path):
    store = ThreadCursorStore(tmp_path / "cursors.json")
    store.advance("t1", cursor="c1", last_message_id="m1")
    store.advance("t2", cursor="c2", last_message_id="m2")

    assert store.get("t1") == CursorState(cursor="c1", last_message_id="m1")
    assert store.get("t2") == CursorState(cursor="c2", last_message_id="m2")


def test_known_thread_ids_empty_when_no_file(tmp_path):
    store = ThreadCursorStore(tmp_path / "cursors.json")
    assert store.known_thread_ids() == []


def test_known_thread_ids_lists_all_tracked_threads(tmp_path):
    store = ThreadCursorStore(tmp_path / "cursors.json")
    store.advance("t1", cursor="c1", last_message_id="m1")
    store.advance("t2", cursor="c2", last_message_id="m2")

    assert sorted(store.known_thread_ids()) == ["t1", "t2"]


# ---------------------------------------------------------------------------
# ThreadCursorStore — persistence (restart-replay safety)
# ---------------------------------------------------------------------------


def test_restart_loads_persisted_state(tmp_path):
    path = tmp_path / "cursors.json"

    # First "process": advance cursor and exit.
    store_a = ThreadCursorStore(path)
    store_a.advance("t1", cursor="cur-50", last_message_id="msg-50")

    # Second "process": new store object, same path — must see previous state.
    store_b = ThreadCursorStore(path)
    assert store_b.get("t1") == CursorState(cursor="cur-50", last_message_id="msg-50")


def test_no_replay_after_restart(tmp_path):
    """Simulate: process message, restart, verify no double-processing."""
    path = tmp_path / "cursors.json"
    messages = [
        {"message_id": "msg-1", "body": {"type": "ping"}},
        {"message_id": "msg-2", "body": {"type": "pong"}},
    ]

    # First run: process both messages, advance cursor to msg-2.
    store = ThreadCursorStore(path)
    unseen_first_run = filter_unseen(messages, processed_ids=set())
    assert len(unseen_first_run) == 2
    store.advance("t1", cursor="cur-2", last_message_id="msg-2")

    # Restart: new store, same path. Reload state.
    store_after_restart = ThreadCursorStore(path)
    state = store_after_restart.get("t1")
    assert state is not None

    # Simulate cursor-based polling returning only new messages after cursor,
    # plus idempotent guard using last_message_id as processed_ids.
    unseen_after_restart = filter_unseen(messages, processed_ids={state.last_message_id})
    # msg-2 is excluded; msg-1 is not in processed_ids but would be before cursor in real poll
    assert all(m["message_id"] != "msg-2" for m in unseen_after_restart)


def test_atomic_write_no_tmp_file_left(tmp_path):
    store = ThreadCursorStore(tmp_path / "cursors.json")
    store.advance("t1", cursor="c1", last_message_id="m1")

    assert not list(tmp_path.glob("*.tmp"))


def test_parent_directory_created_if_missing(tmp_path):
    nested_path = tmp_path / "deep" / "dir" / "cursors.json"
    store = ThreadCursorStore(nested_path)
    store.advance("t1", cursor="c1", last_message_id="m1")

    assert nested_path.exists()


def test_persisted_json_is_valid(tmp_path):
    path = tmp_path / "cursors.json"
    store = ThreadCursorStore(path)
    store.advance("t1", cursor="cursor-abc", last_message_id="msg-xyz")

    raw = json.loads(path.read_text())
    assert raw == {"t1": {"cursor": "cursor-abc", "last_message_id": "msg-xyz"}}


# ---------------------------------------------------------------------------
# filter_unseen — idempotency and filtering
# ---------------------------------------------------------------------------


def test_filter_unseen_empty_processed_ids_returns_all(tmp_path):
    messages = [
        {"message_id": "m1", "body": {}},
        {"message_id": "m2", "body": {}},
    ]
    assert filter_unseen(messages, processed_ids=set()) == messages


def test_filter_unseen_excludes_processed_messages():
    messages = [
        {"message_id": "m1", "body": {}},
        {"message_id": "m2", "body": {}},
        {"message_id": "m3", "body": {}},
    ]
    result = filter_unseen(messages, processed_ids={"m1", "m3"})
    assert [m["message_id"] for m in result] == ["m2"]


def test_filter_unseen_all_processed_returns_empty():
    messages = [
        {"message_id": "m1", "body": {}},
        {"message_id": "m2", "body": {}},
    ]
    assert filter_unseen(messages, processed_ids={"m1", "m2"}) == []


def test_filter_unseen_preserves_original_order():
    messages = [
        {"message_id": "m3"},
        {"message_id": "m1"},
        {"message_id": "m2"},
    ]
    result = filter_unseen(messages, processed_ids={"m1"})
    assert [m["message_id"] for m in result] == ["m3", "m2"]


def test_filter_unseen_idempotent():
    messages = [
        {"message_id": "m1", "body": {}},
        {"message_id": "m2", "body": {}},
    ]
    first = filter_unseen(messages, processed_ids={"m1"})
    # Calling again with the same processed_ids produces the same result.
    second = filter_unseen(messages, processed_ids={"m1"})
    assert first == second


def test_filter_unseen_does_not_mutate_input():
    messages = [
        {"message_id": "m1"},
        {"message_id": "m2"},
    ]
    original = list(messages)
    filter_unseen(messages, processed_ids={"m1"})
    assert messages == original


def test_filter_unseen_message_without_id_passes_through():
    messages = [
        {"body": "no id here"},
        {"message_id": "m1"},
    ]
    result = filter_unseen(messages, processed_ids={"m1"})
    assert len(result) == 1
    assert result[0].get("message_id") is None
