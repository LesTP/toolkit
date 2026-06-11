"""Tests for ClankmatesClient host-side operations (step 4.2)."""

import json
import subprocess
from pathlib import Path

import pytest

from toolkit.clankmates_client import ClankmatesClient, ClankmatesError


def ok_runner(*responses):
    """Return a (runner, calls) pair. Runner yields successive JSON responses."""
    calls = []
    resp_iter = iter(responses)

    def runner(argv, **kwargs):
        calls.append(argv)
        resp = next(resp_iter)
        return subprocess.CompletedProcess(argv, 0, stdout=resp, stderr="")

    return runner, calls


# ---------------------------------------------------------------------------
# send / reply — updated keyword-only signatures
# ---------------------------------------------------------------------------


def test_send_body_string():
    runner, calls = ok_runner('{"sent":true}')
    client = ClankmatesClient(runner=runner)
    result = client.send("p", "@r", body="Hello world")
    assert result == {"sent": True}
    assert calls[0] == [
        "clankm", "--profile", "p", "inbox", "send", "@r", "--body", "Hello world", "--json"
    ]


def test_send_payload_dict():
    payload = {"type": "join_game", "game_id": "g1"}
    runner, calls = ok_runner('{"sent":true}')
    client = ClankmatesClient(runner=runner)
    client.send("p", "@r", payload=payload)
    expected_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    assert calls[0] == [
        "clankm", "--profile", "p", "inbox", "send", "@r", "--payload", expected_json, "--json"
    ]


def test_send_body_file(tmp_path):
    f = tmp_path / "msg.md"
    f.write_text("Hello\nWorld")
    runner, calls = ok_runner('{"sent":true}')
    client = ClankmatesClient(runner=runner)
    client.send("p", "@r", body_file=f)
    assert calls[0] == [
        "clankm", "--profile", "p", "inbox", "send", "@r", "--body-file", str(f), "--json"
    ]


def test_send_payload_file(tmp_path):
    f = tmp_path / "payload.json"
    f.write_text('{"type":"x"}')
    runner, calls = ok_runner('{"sent":true}')
    client = ClankmatesClient(runner=runner)
    client.send("p", "@r", payload_file=f)
    assert calls[0] == [
        "clankm", "--profile", "p", "inbox", "send", "@r", "--payload-file", str(f), "--json"
    ]


def test_send_optional_flags():
    runner, calls = ok_runner('{"sent":true}')
    client = ClankmatesClient(runner=runner)
    client.send(
        "p", "@r",
        body="hi",
        from_channel="chan1",
        context_post_id="post-1",
        channel_token="tok-1",
    )
    argv = calls[0]
    assert "--from-channel" in argv and argv[argv.index("--from-channel") + 1] == "chan1"
    assert "--context-post-id" in argv and argv[argv.index("--context-post-id") + 1] == "post-1"
    assert "--channel-token" in argv and argv[argv.index("--channel-token") + 1] == "tok-1"


def test_send_mutex_no_args_raises():
    client = ClankmatesClient(runner=lambda *a, **k: None)
    with pytest.raises(ValueError, match="exactly one"):
        client.send("p", "@r")


def test_send_mutex_two_args_raises():
    client = ClankmatesClient(runner=lambda *a, **k: None)
    with pytest.raises(ValueError, match="exactly one"):
        client.send("p", "@r", body="hi", payload={"type": "x"})


def test_reply_payload_dict():
    payload = {"type": "order_package", "orders": []}
    runner, calls = ok_runner('{"ok":true}')
    client = ClankmatesClient(runner=runner)
    client.reply("p", "t1", payload=payload)
    expected_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    assert calls[0] == [
        "clankm", "--profile", "p", "inbox", "reply", "t1",
        "--payload", expected_json, "--json",
    ]


def test_reply_body_string():
    runner, calls = ok_runner('{"ok":true}')
    client = ClankmatesClient(runner=runner)
    client.reply("p", "t1", body="Thanks!")
    assert calls[0] == [
        "clankm", "--profile", "p", "inbox", "reply", "t1", "--body", "Thanks!", "--json"
    ]


def test_reply_with_channel_token():
    runner, calls = ok_runner('{"ok":true}')
    client = ClankmatesClient(runner=runner)
    client.reply("p", "t1", body="hi", channel_token="tok-x")
    argv = calls[0]
    assert "--channel-token" in argv and argv[argv.index("--channel-token") + 1] == "tok-x"


def test_reply_mutex_no_args_raises():
    client = ClankmatesClient(runner=lambda *a, **k: None)
    with pytest.raises(ValueError, match="exactly one"):
        client.reply("p", "t1")


# ---------------------------------------------------------------------------
# post_publish
# ---------------------------------------------------------------------------


def test_post_publish_body():
    runner, calls = ok_runner('{"id":"post-1"}')
    client = ClankmatesClient(runner=runner)
    result = client.post_publish("p", channel="news", body="Hello post")
    assert result == {"id": "post-1"}
    assert calls[0] == [
        "clankm", "--profile", "p", "post", "publish",
        "--channel", "news", "--body", "Hello post", "--json",
    ]


def test_post_publish_body_file(tmp_path):
    f = tmp_path / "post.md"
    f.write_text("Hello\nWorld")
    runner, calls = ok_runner('{"id":"p1"}')
    client = ClankmatesClient(runner=runner)
    client.post_publish("p", channel="news", body_file=f)
    assert calls[0] == [
        "clankm", "--profile", "p", "post", "publish",
        "--channel", "news", "--body-file", str(f), "--json",
    ]


def test_post_publish_with_channel_token():
    runner, calls = ok_runner('{"id":"p1"}')
    client = ClankmatesClient(runner=runner)
    client.post_publish("p", channel="news", body="hi", channel_token="tok-y")
    argv = calls[0]
    assert "--channel-token" in argv and argv[argv.index("--channel-token") + 1] == "tok-y"


def test_post_publish_mutex_no_args_raises():
    client = ClankmatesClient(runner=lambda *a, **k: None)
    with pytest.raises(ValueError, match="exactly one"):
        client.post_publish("p", channel="news")


def test_post_public_list():
    runner, calls = ok_runner('{"items":[]}')
    client = ClankmatesClient(runner=runner)
    result = client.post_public_list("p", "@pub", "news", limit=10, cursor="cur1")
    assert result == {"items": []}
    assert calls[0] == [
        "clankm", "--profile", "p", "post", "public-list", "@pub", "news",
        "--limit", "10", "--cursor", "cur1", "--json",
    ]


def test_post_public_list_no_pagination():
    runner, calls = ok_runner('{"items":[]}')
    client = ClankmatesClient(runner=runner)
    client.post_public_list("p", "@pub", "news")
    assert "--limit" not in calls[0]
    assert "--cursor" not in calls[0]


# ---------------------------------------------------------------------------
# channel management
# ---------------------------------------------------------------------------


def test_channel_create_with_description():
    runner, calls = ok_runner('{"type":"channel","id":"uuid-1"}')
    client = ClankmatesClient(runner=runner)
    result = client.channel_create("p", name="arena", description="Arena channel")
    assert result["type"] == "channel"
    assert calls[0] == [
        "clankm", "--profile", "p", "channel", "create", "arena",
        "--description", "Arena channel", "--json",
    ]


def test_channel_create_no_description():
    runner, calls = ok_runner('{"type":"channel"}')
    client = ClankmatesClient(runner=runner)
    client.channel_create("p", name="arena")
    assert "--description" not in calls[0]
    assert calls[0] == ["clankm", "--profile", "p", "channel", "create", "arena", "--json"]


def test_channel_list():
    runner, calls = ok_runner('{"items":[]}')
    client = ClankmatesClient(runner=runner)
    result = client.channel_list("p")
    assert result == {"items": []}
    assert calls[0] == ["clankm", "--profile", "p", "channel", "list", "--json"]


def test_channel_get():
    runner, calls = ok_runner('{"type":"channel","id":"uuid-1"}')
    client = ClankmatesClient(runner=runner)
    result = client.channel_get("p", "uuid-1")
    assert result["id"] == "uuid-1"
    assert calls[0] == ["clankm", "--profile", "p", "channel", "get", "uuid-1", "--json"]


def test_channel_publish_public():
    runner, calls = ok_runner('{"type":"channel"}')
    client = ClankmatesClient(runner=runner)
    client.channel_publish_public("p", "arena")
    assert calls[0] == [
        "clankm", "--profile", "p", "channel", "publish-public", "arena", "--json"
    ]


def test_channel_unpublish_public():
    runner, calls = ok_runner('{"type":"channel"}')
    client = ClankmatesClient(runner=runner)
    client.channel_unpublish_public("p", "arena")
    assert calls[0] == [
        "clankm", "--profile", "p", "channel", "unpublish-public", "arena", "--json"
    ]


def test_channel_delete():
    runner, calls = ok_runner('{"ok":true,"id":"uuid-1"}')
    client = ClankmatesClient(runner=runner)
    result = client.channel_delete("p", "uuid-1")
    assert result == {"ok": True, "id": "uuid-1"}
    assert calls[0] == ["clankm", "--profile", "p", "channel", "delete", "uuid-1", "--json"]


# ---------------------------------------------------------------------------
# channel tokens
# ---------------------------------------------------------------------------


TOKEN_RESPONSE = json.dumps({
    "id": "tok-id",
    "name": "bot",
    "token": "secret-token-value",
    "expires_at": None,
    "issued_at": "2026-01-01T00:00:00Z",
})


def test_channel_token_issue():
    runner, calls = ok_runner(TOKEN_RESPONSE)
    client = ClankmatesClient(runner=runner)
    result = client.channel_token_issue("p", "arena", name="bot")
    assert result["token"] == "secret-token-value"
    assert calls[0] == [
        "clankm", "--profile", "p", "channel", "token", "issue", "arena",
        "--name", "bot", "--json",
    ]


def test_channel_token_issue_flags():
    runner, calls = ok_runner(TOKEN_RESPONSE)
    client = ClankmatesClient(runner=runner)
    client.channel_token_issue("p", "arena", name="bot", save=True, token_only=True)
    assert "--save" in calls[0]
    assert "--token-only" in calls[0]


def test_channel_token_issue_no_flags_by_default():
    runner, calls = ok_runner(TOKEN_RESPONSE)
    client = ClankmatesClient(runner=runner)
    client.channel_token_issue("p", "arena", name="bot")
    assert "--save" not in calls[0]
    assert "--token-only" not in calls[0]


def test_channel_token_list():
    runner, calls = ok_runner('{"items":[{"id":"tok-id","name":"bot"}]}')
    client = ClankmatesClient(runner=runner)
    result = client.channel_token_list("p", "arena")
    assert result["items"][0]["id"] == "tok-id"
    assert calls[0] == [
        "clankm", "--profile", "p", "channel", "token", "list", "arena", "--json"
    ]


def test_channel_token_revoke():
    runner, calls = ok_runner('{"id":"tok-id","name":"bot"}')
    client = ClankmatesClient(runner=runner)
    result = client.channel_token_revoke("p", "tok-id")
    assert result == {"id": "tok-id", "name": "bot"}
    assert calls[0] == [
        "clankm", "--profile", "p", "channel", "token", "revoke", "tok-id", "--json"
    ]


# ---------------------------------------------------------------------------
# typed-inbox schemas
# ---------------------------------------------------------------------------

SCHEMA_OBJ = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}
SCHEMA_JSON = json.dumps(SCHEMA_OBJ, separators=(",", ":"), sort_keys=True)


def test_schema_show_account():
    runner, calls = ok_runner('{"type":"schema"}')
    client = ClankmatesClient(runner=runner)
    client.schema_show("p", "@handle")
    assert calls[0] == ["clankm", "--profile", "p", "schema", "show", "@handle", "--json"]


def test_schema_show_channel():
    runner, calls = ok_runner('{"type":"schema"}')
    client = ClankmatesClient(runner=runner)
    client.schema_show("p", "@handle/arena")
    assert calls[0] == ["clankm", "--profile", "p", "schema", "show", "@handle/arena", "--json"]


def test_schema_set_account_inline():
    runner, calls = ok_runner('{"type":"schema"}')
    client = ClankmatesClient(runner=runner)
    client.schema_set_account("p", schema=SCHEMA_OBJ)
    assert calls[0] == [
        "clankm", "--profile", "p", "schema", "account", "set", "--schema", SCHEMA_JSON, "--json"
    ]


def test_schema_set_account_file(tmp_path):
    f = tmp_path / "schema.json"
    f.write_text(SCHEMA_JSON)
    runner, calls = ok_runner('{"type":"schema"}')
    client = ClankmatesClient(runner=runner)
    client.schema_set_account("p", schema_file=f)
    assert calls[0] == [
        "clankm", "--profile", "p", "schema", "account", "set", "--schema-file", str(f), "--json"
    ]


def test_schema_set_account_mutex_no_args_raises():
    client = ClankmatesClient(runner=lambda *a, **k: None)
    with pytest.raises(ValueError, match="exactly one"):
        client.schema_set_account("p")


def test_schema_set_account_mutex_two_args_raises():
    client = ClankmatesClient(runner=lambda *a, **k: None)
    with pytest.raises(ValueError, match="exactly one"):
        client.schema_set_account("p", schema=SCHEMA_OBJ, schema_file="/tmp/s.json")


def test_schema_set_channel_inline():
    runner, calls = ok_runner('{"type":"schema"}')
    client = ClankmatesClient(runner=runner)
    client.schema_set_channel("p", "arena", schema=SCHEMA_OBJ)
    assert calls[0] == [
        "clankm", "--profile", "p", "schema", "channel", "set", "arena",
        "--schema", SCHEMA_JSON, "--json",
    ]


def test_schema_set_channel_file(tmp_path):
    f = tmp_path / "schema.json"
    f.write_text(SCHEMA_JSON)
    runner, calls = ok_runner('{"type":"schema"}')
    client = ClankmatesClient(runner=runner)
    client.schema_set_channel("p", "arena", schema_file=f)
    assert calls[0] == [
        "clankm", "--profile", "p", "schema", "channel", "set", "arena",
        "--schema-file", str(f), "--json",
    ]


def test_schema_remove_account():
    runner, calls = ok_runner('{"ok":true}')
    client = ClankmatesClient(runner=runner)
    client.schema_remove_account("p")
    assert calls[0] == ["clankm", "--profile", "p", "schema", "account", "remove", "--json"]


def test_schema_remove_channel():
    runner, calls = ok_runner('{"ok":true}')
    client = ClankmatesClient(runner=runner)
    client.schema_remove_channel("p", "arena")
    assert calls[0] == [
        "clankm", "--profile", "p", "schema", "channel", "remove", "arena", "--json"
    ]


def test_schema_acceptance_account_accept():
    runner, calls = ok_runner('{"ok":true}')
    client = ClankmatesClient(runner=runner)
    client.schema_acceptance_account("p", "accept-valid-typed-email")
    assert calls[0] == [
        "clankm", "--profile", "p", "schema", "account", "acceptance",
        "--mode", "accept-valid-typed-email", "--json",
    ]


def test_schema_acceptance_account_screen():
    runner, calls = ok_runner('{"ok":true}')
    client = ClankmatesClient(runner=runner)
    client.schema_acceptance_account("p", "screen-unknown-senders")
    assert calls[0] == [
        "clankm", "--profile", "p", "schema", "account", "acceptance",
        "--mode", "screen-unknown-senders", "--json",
    ]


def test_schema_acceptance_channel():
    runner, calls = ok_runner('{"ok":true}')
    client = ClankmatesClient(runner=runner)
    client.schema_acceptance_channel("p", "arena", "screen-unknown-senders")
    assert calls[0] == [
        "clankm", "--profile", "p", "schema", "channel", "acceptance",
        "arena", "--mode", "screen-unknown-senders", "--json",
    ]


def test_schema_acceptance_channel_accept():
    runner, calls = ok_runner('{"ok":true}')
    client = ClankmatesClient(runner=runner)
    client.schema_acceptance_channel("p", "arena", "accept-valid-typed-email")
    assert calls[0] == [
        "clankm", "--profile", "p", "schema", "channel", "acceptance",
        "arena", "--mode", "accept-valid-typed-email", "--json",
    ]


# ---------------------------------------------------------------------------
# error propagation for host-side methods
# ---------------------------------------------------------------------------


def test_channel_create_propagates_nonzero_exit():
    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not found")

    client = ClankmatesClient(runner=runner)
    with pytest.raises(ClankmatesError) as exc_info:
        client.channel_create("p", name="arena")
    assert exc_info.value.returncode == 1
    assert exc_info.value.stderr == "not found"


def test_schema_set_channel_propagates_nonzero_exit():
    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="schema invalid")

    client = ClankmatesClient(runner=runner)
    with pytest.raises(ClankmatesError) as exc_info:
        client.schema_set_channel("p", "arena", schema={"type": "object"})
    assert exc_info.value.returncode == 2
