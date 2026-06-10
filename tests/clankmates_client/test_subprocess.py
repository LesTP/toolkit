import json
import subprocess

import pytest

from toolkit.clankmates_client import ClankmatesClient, ClankmatesError


def test_reply_uses_exact_clankm_argv_and_json_body():
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout='{"ok":true}', stderr="")

    client = ClankmatesClient(runner=runner)
    body = {"type": "order_package", "orders": []}

    assert client.reply("p1", "thread-1", body) == {"ok": True}
    assert calls[0][0] == [
        "clankm",
        "--profile",
        "p1",
        "inbox",
        "reply",
        "thread-1",
        "--body",
        json.dumps(body, separators=(",", ":"), sort_keys=True),
        "--json",
    ]


def test_adapter_methods_parse_json_and_build_expected_commands():
    calls = []
    responses = iter(
        [
            '{"handle":"bluebot"}',
            '{"threads":[]}',
            '{"messages":[]}',
            '{"archived":true}',
            '{"sent":true}',
        ]
    )

    def runner(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=next(responses), stderr="")

    client = ClankmatesClient(runner=runner)

    assert client.whoami("p") == {"handle": "bluebot"}
    assert client.list_threads("p") == {"threads": []}
    assert client.show_thread("p", "t1", limit=3) == {"messages": []}
    assert client.archive_thread("p", "t1") == {"archived": True}
    assert client.send("p", "@server", {"type": "join_game"}) == {"sent": True}
    assert calls == [
        ["clankm", "--profile", "p", "auth", "whoami", "--json"],
        ["clankm", "--profile", "p", "inbox", "list", "--status", "all", "--json"],
        ["clankm", "--profile", "p", "inbox", "show", "t1", "--limit", "3", "--json"],
        ["clankm", "--profile", "p", "inbox", "archive", "t1", "--json"],
        [
            "clankm",
            "--profile",
            "p",
            "inbox",
            "send",
            "@server",
            "--body",
            '{"type":"join_game"}',
            "--json",
        ],
    ]


def test_non_zero_exit_returns_structured_error():
    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 17, stdout="out", stderr="err")

    client = ClankmatesClient(runner=runner)

    with pytest.raises(ClankmatesError) as exc_info:
        client.whoami("p")

    assert exc_info.value.to_dict() == {
        "ok": False,
        "command": ["clankm", "--profile", "p", "auth", "whoami", "--json"],
        "returncode": 17,
        "stdout": "out",
        "stderr": "err",
    }


def test_malformed_json_returns_structured_error():
    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="{bad json", stderr="")

    client = ClankmatesClient(runner=runner)

    with pytest.raises(ClankmatesError) as exc_info:
        client.list_threads("p")

    assert exc_info.value.to_dict()["decode_error"].startswith("Expecting property name")


def test_missing_clankm_binary_returns_structured_error():
    def runner(argv, **kwargs):
        raise FileNotFoundError("clankm")

    client = ClankmatesClient(runner=runner)

    with pytest.raises(ClankmatesError) as exc_info:
        client.whoami("p")

    payload = exc_info.value.to_dict()
    assert payload["command"] == ["clankm", "--profile", "p", "auth", "whoami", "--json"]
    assert payload["returncode"] is None
    assert payload["stderr"] == "clankm"


def test_timeout_returns_structured_error():
    def runner(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 5, output="partial out", stderr="partial err")

    client = ClankmatesClient(runner=runner)

    with pytest.raises(ClankmatesError) as exc_info:
        client.whoami("p")

    payload = exc_info.value.to_dict()
    assert payload["returncode"] is None
    assert payload["timeout"] == 5
    assert payload["stdout"] == "partial out"
    assert payload["stderr"] == "partial err"
