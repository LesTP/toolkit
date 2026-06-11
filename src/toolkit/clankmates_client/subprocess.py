"""Clankmates subprocess wrapper.

SOURCE: clanker-courts-player-client/skills/clanker-courts-operator/scripts/clanker_courts_player/clankmates.py
Commit: 42d192f97be225648894b62688ebdbd1978b5597
Date: 2026-06-10
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
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

    # --- Player-side ops (vendored from 4.1) ---

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

    def send(
        self,
        profile: str,
        recipient: str,
        *,
        body: str | None = None,
        body_file: str | Path | None = None,
        payload: dict | None = None,
        payload_file: str | Path | None = None,
        from_channel: str | None = None,
        context_post_id: str | None = None,
        channel_token: str | None = None,
    ) -> dict[str, Any]:
        """Send a message. Exactly one of body/body_file/payload/payload_file required.
        Typed inboxes require payload/payload_file; server silently rejects body-encoded typed payloads."""
        argv = ["--profile", profile, "inbox", "send", recipient]
        argv.extend(_content_args(body, body_file, payload, payload_file))
        if from_channel is not None:
            argv.extend(["--from-channel", from_channel])
        if context_post_id is not None:
            argv.extend(["--context-post-id", context_post_id])
        if channel_token is not None:
            argv.extend(["--channel-token", channel_token])
        argv.append("--json")
        return self._run_json(argv)

    def reply(
        self,
        profile: str,
        thread_id: str,
        *,
        body: str | None = None,
        body_file: str | Path | None = None,
        payload: dict | None = None,
        payload_file: str | Path | None = None,
        channel_token: str | None = None,
    ) -> dict[str, Any]:
        """Reply to a thread. Exactly one of body/body_file/payload/payload_file required."""
        argv = ["--profile", profile, "inbox", "reply", thread_id]
        argv.extend(_content_args(body, body_file, payload, payload_file))
        if channel_token is not None:
            argv.extend(["--channel-token", channel_token])
        argv.append("--json")
        return self._run_json(argv)

    # --- Posts ---

    def post_publish(
        self,
        profile: str,
        *,
        channel: str,
        body: str | None = None,
        body_file: str | Path | None = None,
        channel_token: str | None = None,
    ) -> dict[str, Any]:
        """Publish a post. Exactly one of body/body_file required.
        Use body_file for multi-line content (inline quoting loses newlines)."""
        argv = ["--profile", profile, "post", "publish", "--channel", channel]
        argv.extend(_body_args(body, body_file))
        if channel_token is not None:
            argv.extend(["--channel-token", channel_token])
        argv.append("--json")
        return self._run_json(argv)

    def post_public_list(
        self,
        profile: str,
        public_handle: str,
        channel_name: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List public posts for a channel. Returns {items: [...]}."""
        argv = ["--profile", profile, "post", "public-list", public_handle, channel_name]
        if limit is not None:
            argv.extend(["--limit", str(limit)])
        if cursor is not None:
            argv.extend(["--cursor", cursor])
        argv.append("--json")
        return self._run_json(argv)

    # --- Channel management ---

    def channel_create(
        self, profile: str, *, name: str, description: str | None = None
    ) -> dict[str, Any]:
        argv = ["--profile", profile, "channel", "create", name]
        if description is not None:
            argv.extend(["--description", description])
        argv.append("--json")
        return self._run_json(argv)

    def channel_list(self, profile: str) -> dict[str, Any]:
        """Returns {items: [...]}."""
        return self._run_json(["--profile", profile, "channel", "list", "--json"])

    def channel_get(self, profile: str, name_or_uuid: str) -> dict[str, Any]:
        return self._run_json(["--profile", profile, "channel", "get", name_or_uuid, "--json"])

    def channel_publish_public(self, profile: str, name_or_uuid: str) -> dict[str, Any]:
        return self._run_json(
            ["--profile", profile, "channel", "publish-public", name_or_uuid, "--json"]
        )

    def channel_unpublish_public(self, profile: str, name_or_uuid: str) -> dict[str, Any]:
        return self._run_json(
            ["--profile", profile, "channel", "unpublish-public", name_or_uuid, "--json"]
        )

    def channel_delete(self, profile: str, name_or_uuid: str) -> dict[str, Any]:
        """Returns {ok: True, id: <uuid>}."""
        return self._run_json(["--profile", profile, "channel", "delete", name_or_uuid, "--json"])

    # --- Channel tokens ---

    def channel_token_issue(
        self,
        profile: str,
        channel: str,
        *,
        name: str,
        save: bool = False,
        token_only: bool = False,
    ) -> dict[str, Any]:
        """Issue a channel token. Returns {id, name, token, expires_at, issued_at}.
        Token value ONLY returned at issue time; list endpoint omits it."""
        argv = ["--profile", profile, "channel", "token", "issue", channel, "--name", name]
        if save:
            argv.append("--save")
        if token_only:
            argv.append("--token-only")
        argv.append("--json")
        return self._run_json(argv)

    def channel_token_list(self, profile: str, channel: str) -> dict[str, Any]:
        """Returns {items: [...]} without token values."""
        return self._run_json(
            ["--profile", profile, "channel", "token", "list", channel, "--json"]
        )

    def channel_token_revoke(self, profile: str, token_id: str) -> dict[str, Any]:
        """Returns {id, name}."""
        return self._run_json(
            ["--profile", profile, "channel", "token", "revoke", token_id, "--json"]
        )

    # --- Typed-inbox schemas ---

    def schema_show(self, profile: str, address: str) -> dict[str, Any]:
        """Show inbox schema. address: '@handle' for account, '@handle/channel' for channel."""
        return self._run_json(["--profile", profile, "schema", "show", address, "--json"])

    def schema_set_account(
        self,
        profile: str,
        *,
        schema: dict | None = None,
        schema_file: str | Path | None = None,
    ) -> dict[str, Any]:
        """Set typed-inbox schema for the account.
        Side-effect: auto-flips external_email_acceptance to accept_valid_typed_email."""
        argv = ["--profile", profile, "schema", "account", "set"]
        argv.extend(_schema_args(schema, schema_file))
        argv.append("--json")
        return self._run_json(argv)

    def schema_set_channel(
        self,
        profile: str,
        channel: str,
        *,
        schema: dict | None = None,
        schema_file: str | Path | None = None,
    ) -> dict[str, Any]:
        """Set typed-inbox schema for a channel.
        Side-effect: auto-flips external_email_acceptance to accept_valid_typed_email."""
        argv = ["--profile", profile, "schema", "channel", "set", channel]
        argv.extend(_schema_args(schema, schema_file))
        argv.append("--json")
        return self._run_json(argv)

    def schema_remove_account(self, profile: str) -> dict[str, Any]:
        """Remove account schema. Resets external_email_acceptance to screen_unknown_senders."""
        return self._run_json(["--profile", profile, "schema", "account", "remove", "--json"])

    def schema_remove_channel(self, profile: str, channel: str) -> dict[str, Any]:
        """Remove channel schema. Resets external_email_acceptance to screen_unknown_senders."""
        return self._run_json(
            ["--profile", profile, "schema", "channel", "remove", channel, "--json"]
        )

    def schema_acceptance_account(self, profile: str, mode: str) -> dict[str, Any]:
        """Override account external_email_acceptance.
        mode: 'screen-unknown-senders' | 'accept-valid-typed-email'."""
        return self._run_json(
            ["--profile", profile, "schema", "account", "acceptance", "--mode", mode, "--json"]
        )

    def schema_acceptance_channel(self, profile: str, channel: str, mode: str) -> dict[str, Any]:
        """Override channel external_email_acceptance.
        mode: 'screen-unknown-senders' | 'accept-valid-typed-email'."""
        return self._run_json(
            [
                "--profile", profile, "schema", "channel", "acceptance",
                channel, "--mode", mode, "--json",
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


def _content_args(
    body: str | None,
    body_file: str | Path | None,
    payload: dict | None,
    payload_file: str | Path | None,
) -> list[str]:
    given = sum([body is not None, body_file is not None, payload is not None, payload_file is not None])
    if given != 1:
        raise ValueError(
            f"exactly one of body/body_file/payload/payload_file required, got {given}"
        )
    if body is not None:
        return ["--body", body]
    if body_file is not None:
        return ["--body-file", str(body_file)]
    if payload is not None:
        return ["--payload", _json_compact(payload)]
    return ["--payload-file", str(payload_file)]


def _body_args(body: str | None, body_file: str | Path | None) -> list[str]:
    given = sum([body is not None, body_file is not None])
    if given != 1:
        raise ValueError(f"exactly one of body/body_file required, got {given}")
    if body is not None:
        return ["--body", body]
    return ["--body-file", str(body_file)]


def _schema_args(schema: dict | None, schema_file: str | Path | None) -> list[str]:
    given = sum([schema is not None, schema_file is not None])
    if given != 1:
        raise ValueError(f"exactly one of schema/schema_file required, got {given}")
    if schema is not None:
        return ["--schema", _json_compact(schema)]
    return ["--schema-file", str(schema_file)]


def _json_compact(data: dict[str, Any]) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def _coerce_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
