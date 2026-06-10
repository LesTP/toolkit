"""Thread cursor and processed-message-ID tracking helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CursorState:
    cursor: str
    last_message_id: str


class ThreadCursorStore:
    """JSON-backed persistence for {thread_id: (cursor, last_message_id)} pairs.

    Restart-safe: consumers construct a new store from the same path after restart
    and will not re-process already-handled messages.

    Storage format: {"<thread_id>": {"cursor": "...", "last_message_id": "..."}, ...}
    Writes are atomic (temp-file + os.replace).
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def get(self, thread_id: str) -> CursorState | None:
        entry = self._load().get(thread_id)
        if entry is None:
            return None
        return CursorState(cursor=entry["cursor"], last_message_id=entry["last_message_id"])

    def advance(self, thread_id: str, *, cursor: str, last_message_id: str) -> None:
        data = self._load()
        data[thread_id] = {"cursor": cursor, "last_message_id": last_message_id}
        self._save(data)

    def known_thread_ids(self) -> list[str]:
        return list(self._load().keys())

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        with self._path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict):
            raise ValueError("cursor store file must contain a JSON object")
        return payload

    def _save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f".{self._path.name}.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, self._path)


def filter_unseen(
    messages: list[dict[str, Any]], *, processed_ids: set[str]
) -> list[dict[str, Any]]:
    """Return decoded messages whose message_id is not in processed_ids, preserving order."""
    return [m for m in messages if m.get("message_id") not in processed_ids]
