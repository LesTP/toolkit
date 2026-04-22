"""Tests for WebSocketTransport — JSON-RPC transport over WebSocket."""

import asyncio
import unittest

websockets = None
try:
    import websockets  # type: ignore[no-redef]
except ImportError:
    pass

import pytest

ws_available = pytest.importorskip("websockets")

from toolkit.json_rpc import WebSocketTransport
from toolkit.json_rpc.types import JsonRpcTransportError


async def _echo_handler(ws: websockets.ServerConnection) -> None:
    """Echo every message back to the client."""
    async for msg in ws:
        await ws.send(msg)


async def _start_server(
    handler=None,
) -> tuple[websockets.Server, str]:
    """Start a local WS server and return (server, url)."""
    handler = handler or _echo_handler
    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, f"ws://127.0.0.1:{port}"


class WebSocketTransportConnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_succeeds(self) -> None:
        server, url = await _start_server()
        try:
            transport = await WebSocketTransport.connect(url, connect_timeout=5.0)
            self.assertTrue(transport.is_alive)
            await transport.close()
        finally:
            server.close()
            await server.wait_closed()

    async def test_connect_times_out_on_unreachable_host(self) -> None:
        # Use a non-routable address to force timeout
        with self.assertRaises(JsonRpcTransportError) as ctx:
            await WebSocketTransport.connect(
                "ws://192.0.2.1:1",  # RFC 5737 TEST-NET
                connect_timeout=0.5,
            )
        self.assertIn("timed out", str(ctx.exception))

    async def test_connect_retries_until_server_appears(self) -> None:
        """Start the server after a short delay; connect() should retry and succeed."""
        # Start on a random port, grab the port, then stop the server
        temp_server, url = await _start_server()
        port = temp_server.sockets[0].getsockname()[1]
        temp_server.close()
        await temp_server.wait_closed()

        # Restart the server on the same port after a delay
        server = None

        async def restart_server():
            await asyncio.sleep(0.3)
            nonlocal server
            server = await websockets.serve(_echo_handler, "127.0.0.1", port)

        restart_task = asyncio.create_task(restart_server())

        try:
            transport = await WebSocketTransport.connect(
                f"ws://127.0.0.1:{port}", connect_timeout=5.0
            )
            self.assertTrue(transport.is_alive)
            await transport.close()
        finally:
            await restart_task
            if server:
                server.close()
                await server.wait_closed()


class WebSocketTransportReadWriteTests(unittest.IsolatedAsyncioTestCase):
    async def test_write_and_read_round_trip(self) -> None:
        server, url = await _start_server()
        try:
            transport = await WebSocketTransport.connect(url, connect_timeout=5.0)
            await transport.write_line('{"id":1,"method":"test"}\n')
            line = await transport.read_line()
            self.assertEqual(line, '{"id":1,"method":"test"}\n')
            await transport.close()
        finally:
            server.close()
            await server.wait_closed()

    async def test_read_bytes_decoded_to_str(self) -> None:
        """Server sends bytes; transport should decode to str."""

        async def bytes_handler(ws: websockets.ServerConnection) -> None:
            async for msg in ws:
                await ws.send(msg.encode("utf-8") if isinstance(msg, str) else msg)

        server, url = await _start_server(bytes_handler)
        try:
            transport = await WebSocketTransport.connect(url, connect_timeout=5.0)
            await transport.write_line('{"id":1}\n')
            line = await transport.read_line()
            self.assertIsInstance(line, str)
            await transport.close()
        finally:
            server.close()
            await server.wait_closed()


class WebSocketTransportErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_write_after_server_disconnect_raises_transport_error(self) -> None:
        server, url = await _start_server()
        transport = await WebSocketTransport.connect(url, connect_timeout=5.0)
        server.close()
        await server.wait_closed()
        # Give the client time to notice the close
        await asyncio.sleep(0.1)

        with self.assertRaises(JsonRpcTransportError):
            await transport.write_line('{"id":1}\n')

    async def test_read_after_server_disconnect_raises_transport_error(self) -> None:
        async def close_immediately(ws: websockets.ServerConnection) -> None:
            await ws.close()

        server, url = await _start_server(close_immediately)
        try:
            transport = await WebSocketTransport.connect(url, connect_timeout=5.0)
            with self.assertRaises(JsonRpcTransportError):
                await transport.read_line()
        finally:
            server.close()
            await server.wait_closed()

    async def test_is_alive_reflects_connection_state(self) -> None:
        async def close_immediately(ws: websockets.ServerConnection) -> None:
            await ws.close()

        server, url = await _start_server(close_immediately)
        try:
            transport = await WebSocketTransport.connect(url, connect_timeout=5.0)
            # After server closes, wait for the close to propagate
            await asyncio.sleep(0.1)
            self.assertFalse(transport.is_alive)
        finally:
            server.close()
            await server.wait_closed()


class WebSocketTransportCloseTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_is_idempotent(self) -> None:
        server, url = await _start_server()
        try:
            transport = await WebSocketTransport.connect(url, connect_timeout=5.0)
            await transport.close()
            await transport.close()  # should not raise
        finally:
            server.close()
            await server.wait_closed()
