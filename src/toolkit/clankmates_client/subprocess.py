"""Clankmates subprocess wrapper.

SOURCE: clanker-courts-player-client/skills/clanker-courts-operator/scripts/clanker_courts_player/clankmates.py
Commit: 42d192f97be225648894b62688ebdbd1978b5597
Date: 2026-06-10
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

Runner = Callable[..., subprocess.CompletedProcess[str]]


class ClankmatesError(RuntimeError):
    def __init__(
        self,
        *,
        command: list[str],
        returncode: int | None,
        stdout: str,
        stderr: str,
        decode_error: str | None = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__(decode_error or stderr or f"clankm exited {returncode}")
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.decode_error = decode_error
        self.timeout = timeout

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }
        if self.decode_error is not None:
            payload["decode_error"] = self.decode_error
        if self.timeout is not None:
            payload["timeout"] = self.timeout
        return payload


class ClankmatesClient:
    def __init__(
        self,
        *,
        clankm_path: str = "clankm",
        runner: Runner | None = None,
        timeout: float = 30,
    ) -> None:
        self.clankm_path = clankm_path
        self.runner = runner or subprocess.run
        self.timeout = timeout

    def whoami(self, profile: str) -> dict[str, Any]:
        return self._run_json(["--profile", profile, "auth", "whoami", "--json"])

    def list_threads(self, profile: str, status: str = "all") -> dict[str, Any]:
        return self._run_json(
            ["--profile", profile, "inbox", "list", "--status", status, "--json"]
        )

    def show_thread(
        self, profile: str, thread_id: str, *, limit: int = 10, cursor: str | None = None
    ) -> dict[str, Any]:
        argv = ["--profile", profile, "inbox", "show", thread_id, "--limit", str(limit)]
        if cursor is not None:
            argv.extend(["--cursor", cursor])
        argv.append("--json")
        return self._run_json(argv)

    def archive_thread(self, profile: str, thread_id: str) -> dict[str, Any]:
        return self._run_json(["--profile", profile, "inbox", "archive", thread_id, "--json"])

    def send(self, profile: str, recipient: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._run_json(
            [
                "--profile",
                profile,
                "inbox",
                "send",
                recipient,
                "--body",
                _json_body(body),
                "--json",
            ]
        )

    def reply(self, profile: str, thread_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._run_json(
            [
                "--profile",
                profile,
                "inbox",
                "reply",
                thread_id,
                "--body",
                _json_body(body),
                "--json",
            ]
        )

    def _run_json(self, args: list[str]) -> dict[str, Any]:
        command = [self.clankm_path, *args]
        try:
            completed = self.runner(
                command,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ClankmatesError(
                command=command,
                returncode=None,
                stdout="",
                stderr=str(exc),
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ClankmatesError(
                command=command,
                returncode=None,
                stdout=_coerce_text(exc.output),
                stderr=_coerce_text(exc.stderr),
                timeout=exc.timeout,
            ) from exc
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if completed.returncode != 0:
            raise ClankmatesError(
                command=command,
                returncode=completed.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        try:
            decoded = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ClankmatesError(
                command=command,
                returncode=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                decode_error=str(exc),
            ) from exc
        if not isinstance(decoded, dict):
            raise ClankmatesError(
                command=command,
                returncode=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                decode_error="expected JSON object",
            )
        return decoded


def _json_body(body: dict[str, Any]) -> str:
    return json.dumps(body, separators=(",", ":"), sort_keys=True)


def _coerce_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
