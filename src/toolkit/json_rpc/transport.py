"""JSON-RPC transport layer — subprocess-backed JSON-line transport."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from .types import JsonRpcTransportError


DEFAULT_SUBPROCESS_STREAM_LIMIT_BYTES = 10 * 1024 * 1024


class JsonRpcTransport(Protocol):
    """Minimal async JSON-line transport for JSON-RPC communication."""

    async def write_line(self, line: str) -> None:
        """Write one JSON-RPC line to the transport."""

    async def read_line(self) -> str:
        """Read one JSON-RPC line from the transport."""

    async def close(self) -> None:
        """Close the transport."""


class SubprocessTransport:
    """JSON-line transport backed by a subprocess."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        if process.stdin is None or process.stdout is None:
            raise JsonRpcTransportError("subprocess stdio pipes are unavailable")

        self.process = process
        self._stdin = process.stdin
        self._stdout = process.stdout

    @classmethod
    async def spawn(
        cls,
        command: str | list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stream_limit: int = DEFAULT_SUBPROCESS_STREAM_LIMIT_BYTES,
    ) -> SubprocessTransport:
        """Launch a subprocess and return a connected transport."""
        if isinstance(command, str):
            args = [command]
        else:
            args = list(command)

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                limit=stream_limit,
            )
        except OSError as exc:
            raise JsonRpcTransportError(
                f"failed to launch subprocess: {exc}"
            ) from exc

        return cls(process)

    @property
    def is_alive(self) -> bool:
        """Return whether the subprocess is still running."""
        return self.process.returncode is None

    async def write_line(self, line: str) -> None:
        """Write one JSON-RPC line to subprocess stdin."""
        try:
            self._stdin.write(line.encode("utf-8"))
            await self._stdin.drain()
        except (BrokenPipeError, ConnectionError) as exc:
            raise JsonRpcTransportError("subprocess stdin is closed") from exc

    async def read_line(self) -> str:
        """Read one JSON-RPC line from subprocess stdout."""
        line = await self._stdout.readline()
        if line == b"":
            raise JsonRpcTransportError("subprocess stdout closed")
        return line.decode("utf-8")

    async def close(self) -> None:
        """Terminate the subprocess gracefully, killing it if needed."""
        if self.process.returncode is not None:
            return

        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()


def encode_json_line(message: dict[str, Any]) -> str:
    """Encode one JSON object as a compact newline-terminated JSON-RPC line."""
    return json.dumps(message, separators=(",", ":")) + "\n"
