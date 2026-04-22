"""JSON-RPC transport layer — WebSocket-backed JSON-line transport."""

from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

from .types import JsonRpcTransportError

LOGGER = logging.getLogger(__name__)

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore[assignment]
    ConnectionClosed = None  # type: ignore[assignment,misc]

DEFAULT_CONNECT_TIMEOUT = 30.0
_RETRY_INTERVAL = 0.5


class WebSocketTransport:
    """JSON-line transport backed by a WebSocket connection."""

    def __init__(self, ws: websockets.ClientConnection) -> None:
        self._ws = ws

    @classmethod
    async def connect(
        cls,
        url: str,
        *,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    ) -> WebSocketTransport:
        """Connect to a WebSocket server, retrying until *connect_timeout* expires."""
        if websockets is None:
            raise JsonRpcTransportError(
                "websockets package is not installed; "
                "install it with: pip install toolkit[ws]"
            )

        deadline = asyncio.get_event_loop().time() + connect_timeout
        last_error: Exception | None = None
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                msg = f"WebSocket connect to {url} timed out after {connect_timeout}s"
                if last_error is not None:
                    msg += f": {last_error}"
                raise JsonRpcTransportError(msg)
            try:
                ws = await asyncio.wait_for(
                    websockets.connect(url),
                    timeout=min(remaining, _RETRY_INTERVAL * 2),
                )
                return cls(ws)
            except Exception as exc:
                last_error = exc
                remaining = deadline - asyncio.get_event_loop().time()
                wait = min(_RETRY_INTERVAL, remaining)
                if wait > 0:
                    await asyncio.sleep(wait)

    @property
    def is_alive(self) -> bool:
        """Return whether the WebSocket connection is still open."""
        return self._ws.close_code is None

    async def write_line(self, line: str) -> None:
        """Write one JSON-RPC line through the WebSocket."""
        try:
            await self._ws.send(line)
        except ConnectionClosed as exc:
            raise JsonRpcTransportError("WebSocket connection closed") from exc

    async def read_line(self) -> str:
        """Read one JSON-RPC line from the WebSocket."""
        try:
            msg = await self._ws.recv()
        except ConnectionClosed as exc:
            raise JsonRpcTransportError("WebSocket connection closed") from exc
        if isinstance(msg, bytes):
            return msg.decode("utf-8")
        return msg

    async def close(self) -> None:
        """Close the WebSocket connection."""
        try:
            await self._ws.close()
        except Exception:
            pass
