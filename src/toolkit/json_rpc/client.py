"""Generic JSON-RPC 2.0 client over async JSON-line transport."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from itertools import count
from typing import Any, Callable, DefaultDict

from .transport import JsonRpcTransport, encode_json_line
from .types import (
    JsonRpcError,
    JsonRpcProtocolError,
    JsonRpcTimeoutError,
    JsonRpcTransportError,
)


DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0


class JsonRpcClient:
    """Generic JSON-RPC 2.0 client with request-response correlation."""

    def __init__(
        self,
        transport: JsonRpcTransport,
        *,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._transport = transport
        self._request_timeout = float(request_timeout)
        self._request_ids = count(1)
        self._connected = False
        self._pending_requests: dict[int | str, asyncio.Future[dict[str, Any]]] = {}
        self._notification_queues: DefaultDict[
            str, asyncio.Queue[dict[str, Any]]
        ] = defaultdict(asyncio.Queue)
        self._server_request_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None
        self._notification_callback: Callable[[dict[str, Any]], None] | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._reader_error: JsonRpcError | None = None

    async def start(self) -> None:
        """Start the reader loop."""
        if self._reader_task is None or self._reader_task.done():
            self._reader_error = None
            self._reader_task = asyncio.create_task(self._reader_loop())
            self._connected = True

    async def stop(self) -> None:
        """Stop reader loop, fail pending requests, close transport."""
        self._connected = False
        task = self._reader_task
        self._reader_task = None
        self._fail_pending_requests(JsonRpcProtocolError("client stopped"))
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        try:
            await self._transport.close()
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        """Return whether the client is initialized and the transport is open."""
        return self._connected

    def build_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        request_id: int | None = None,
    ) -> dict[str, Any]:
        """Build a JSON-RPC request object with a client-generated ID."""
        if not method:
            raise ValueError("method is required")

        request: dict[str, Any] = {
            "id": next(self._request_ids) if request_id is None else request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params
        return request

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for its correlated response."""
        if self._reader_error is not None:
            raise self._reader_error

        request = self.build_request(method, params)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending_requests[request["id"]] = future

        try:
            await self._transport.write_line(encode_json_line(request))
        except Exception:
            self._pending_requests.pop(request["id"], None)
            raise

        try:
            return await asyncio.wait_for(
                future,
                timeout=self._request_timeout if timeout is None else timeout,
            )
        except asyncio.TimeoutError as exc:
            self._pending_requests.pop(request["id"], None)
            raise JsonRpcTimeoutError(f"{method} timed out") from exc

    async def send_notification(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        await self._transport.write_line(encode_json_line(message))

    async def next_notification(
        self, method: str, *, timeout: float | None = None
    ) -> dict[str, Any]:
        """Return the next notification for a method."""
        queue = self._notification_queues[method]
        try:
            return await asyncio.wait_for(
                queue.get(),
                timeout=self._request_timeout if timeout is None else timeout,
            )
        except asyncio.TimeoutError as exc:
            raise JsonRpcTimeoutError(f"{method} notification timed out") from exc

    def on_server_request(
        self, handler: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> None:
        """Register a handler for server-initiated requests."""
        self._server_request_handler = handler

    def on_notification(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a callback invoked for every notification received."""
        self._notification_callback = callback

    async def _reader_loop(self) -> None:
        try:
            while True:
                line = await self._transport.read_line()
                message = self._decode_message(line)
                await self._route_message(message)
        except asyncio.CancelledError:
            raise
        except (JsonRpcTransportError, JsonRpcProtocolError) as exc:
            self._reader_error = exc
            self._connected = False
            self._fail_pending_requests(exc)

    def _decode_message(self, line: str) -> dict[str, Any]:
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JsonRpcProtocolError("received malformed JSON") from exc

        if not isinstance(message, dict):
            raise JsonRpcProtocolError("message is not a JSON object")
        return message

    async def _route_message(self, message: dict[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message):
            self._route_response(message)
            return
        if "id" in message and "method" in message:
            await self._handle_server_request(message)
            return
        if "method" in message:
            self._route_notification(message)
            return
        raise JsonRpcProtocolError("message missing method or response body")

    def _route_response(self, message: dict[str, Any]) -> None:
        request_id = message["id"]
        future = self._pending_requests.pop(request_id, None)
        if future is None:
            # Late response for a timed-out or cancelled request — discard.
            return
        if not future.done():
            future.set_result(message)

    def _route_notification(self, message: dict[str, Any]) -> None:
        method = message["method"]
        if not isinstance(method, str):
            raise JsonRpcProtocolError("notification method is not a string")
        self._notification_queues[method].put_nowait(message)
        if self._notification_callback is not None:
            try:
                self._notification_callback(message)
            except Exception:
                pass  # Don't let callback errors kill the reader loop

    async def _handle_server_request(self, message: dict[str, Any]) -> None:
        if self._server_request_handler is None:
            return
        try:
            response = self._server_request_handler(message)
        except Exception:
            return  # Don't let handler errors kill the reader loop
        await self._transport.write_line(encode_json_line(response))

    def _fail_pending_requests(self, error: JsonRpcError) -> None:
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(error)
        self._pending_requests.clear()
