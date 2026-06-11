"""Smoke test for toolkit.clankmates_client against the live Clankmates server.

Exercises: whoami, list_threads, send (self-ping), show_thread, decode_clankmates_message.
Run from container: cd /home/claude/workspace/toolkit && PYTHONPATH=src python3 tools/smoke_clankmates.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from toolkit.clankmates_client import ClankmatesClient
from toolkit.clankmates_client.decode import decode_clankmates_message

PROFILE = "battlepenguin_bot"
SELF_HANDLE = "@battlepenguin_bot"

client = ClankmatesClient()


def section(label: str) -> None:
    print(f"\n=== {label} ===")


def pretty(data, max_chars: int = 800) -> None:
    text = json.dumps(data, indent=2, sort_keys=True)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... [{len(text) - max_chars} more chars]"
    print(text)


# 1. ping
section("whoami (ping)")
me = client.whoami(PROFILE)
pretty(me)
print(f"-> publicHandle: {me.get('publicHandle')!r}")

# 2. inbox read
section("list_threads (read)")
before = client.list_threads(PROFILE, status="all")
pretty(before)

# extract pre-existing thread IDs to detect the new one after send
def thread_ids(payload: dict) -> set[str]:
    threads = payload.get("threads") or payload.get("data") or []
    ids: set[str] = set()
    for t in threads:
        tid = t.get("id") or t.get("thread_id") or t.get("threadId")
        if tid:
            ids.add(str(tid))
    return ids


ids_before = thread_ids(before)
print(f"-> {len(ids_before)} threads before send")

# 3. self-ping (write)
section("send self-ping (write)")
ping_body = {
    "type": "toolkit_smoke",
    "note": "toolkit.clankmates_client smoke test",
    "from_tool": "toolkit/clankmates_client@phase-4",
}
sent = client.send(PROFILE, recipient=SELF_HANDLE, body=ping_body)
pretty(sent)

# 4. re-list, find new thread
section("list_threads after send")
after = client.list_threads(PROFILE, status="all")
ids_after = thread_ids(after)
new_ids = ids_after - ids_before
print(f"-> {len(ids_after)} threads after send; new: {sorted(new_ids)}")

# 5. show new thread + decode
if new_ids:
    new_id = next(iter(new_ids))
    section(f"show_thread {new_id}")
    detail = client.show_thread(PROFILE, new_id, limit=5)
    pretty(detail, max_chars=1200)

    section("decode messages from new thread")
    raw_messages = (
        detail.get("messages") or detail.get("data") or detail.get("items") or []
    )
    print(f"-> {len(raw_messages)} raw messages to decode")
    for i, raw in enumerate(raw_messages):
        decoded = decode_clankmates_message(raw)
        body = decoded.get("body")
        body_summary = (
            f"type={body.get('type')!r}" if isinstance(body, dict) else f"raw={body!r}"
        )
        print(
            f"  [{i}] msg_id={decoded.get('message_id')} ts={decoded.get('timestamp')} {body_summary}"
        )
else:
    section("no new thread detected")
    print("(skipping show + decode steps)")

section("DONE")
