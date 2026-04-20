# ARCH: JSON-RPC Client

## Purpose
Async JSON-RPC 2.0 client for communicating with subprocess servers over stdio (newline-delimited JSON). Handles message framing, request-response correlation, notification routing, and subprocess lifecycle. Generic — not tied to any specific server protocol.

**Provenance:** Extracted from codexbot's `codex_client.py`, which implements a full JSON-RPC 2.0 client over stdio for the Codex app-server. The transport/framing/correlation layers are protocol-generic; Codex-specific logic (threads, turns, approvals) stays in codexbot as a consumer.

**Second-consumer note:** Currently only codexbot uses this pattern. Phosphene's Scheduler/Orchestrator *may* manage subprocesses (Explorer via Playwright, external tools), but that's speculative. This module is a candidate — include in the toolkit if a second consumer materializes, or build it early if the extraction cost is low enough to justify the cleaner codexbot architecture.

## Public API

### JsonRpcClient

The primary interface. Wraps a transport and provides request-response correlation, notification routing, and a background reader loop.

- **Constructor:** `JsonRpcClient(transport: JsonRpcTransport, *, request_timeout: float = 30.0)`
  - transport: JsonRpcTransport — the underlying line-based transport
  - request_timeout: float — default timeout for `request()` calls

#### Lifecycle

**start**
- **Signature:** `async def start(self) -> None`
- Starts the background reader loop that routes incoming messages to pending request futures or notification queues.

**stop**
- **Signature:** `async def stop(self) -> None`
- Stops the reader loop, fails any pending requests with `JsonRpcTransportError`, and closes the transport.

**is_connected**
- **Signature:** `@property def is_connected(self) -> bool`
- True if the reader loop is running and the transport is open.

#### Requests

**request**
- **Signature:** `async def request(self, method: str, params: dict[str, Any] | None = None, *, timeout: float | None = None) -> dict[str, Any]`
- Sends a JSON-RPC request and waits for the matching response (correlated by request ID).
- **Returns:** The `result` field from the response.
- **Errors:**
  - `JsonRpcTimeoutError` — no response within timeout
  - `JsonRpcTransportError` — transport disconnected while waiting
  - `JsonRpcErrorResponse` — server returned an error response (includes `code` and `message`)

**send_notification**
- **Signature:** `async def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None`
- Sends a JSON-RPC notification (no response expected — no `id` field).

#### Notifications

**next_notification**
- **Signature:** `async def next_notification(self, method: str, *, timeout: float | None = None) -> dict[str, Any]`
- Waits for the next server notification with the given method name. Notifications are queued per-method — multiple consumers can listen on different methods concurrently.
- **Returns:** The full notification message (`{"jsonrpc": "2.0", "method": ..., "params": ...}`)
- **Errors:** `JsonRpcTimeoutError`

#### Server Requests

**on_server_request**
- **Signature:** `def on_server_request(self, handler: Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]) -> None`
- Registers a handler for server-initiated requests. The handler receives the full request message and must return a result dict (or an awaitable of one). If no handler is registered, server requests receive a `method_not_found` error response.

#### Low-level

**build_request**
- **Signature:** `def build_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]`
- Constructs a JSON-RPC request dict with auto-incremented ID. Useful for inspection or manual sending.

### Transport Protocol

```python
class JsonRpcTransport(Protocol):
    async def write_line(self, line: str) -> None: ...
    async def read_line(self) -> str: ...
    async def close(self) -> None: ...
```

A transport reads and writes newline-delimited strings. Each line is one JSON-RPC message.

### SubprocessTransport

Spawns and manages a child process, communicating over its stdin/stdout.

- **Constructor:** `SubprocessTransport(process: asyncio.subprocess.Process)`
  - Takes an already-spawned process. Use the `spawn` classmethod for convenience.

**spawn** (classmethod)
- **Signature:** `@classmethod async def spawn(cls, command: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None, stream_limit: int = 10_485_760) -> SubprocessTransport`
- Spawns the subprocess and returns a connected transport.
- **Errors:** `JsonRpcTransportError` if the process fails to start.

**is_alive**
- **Signature:** `@property def is_alive(self) -> bool`
- True if the subprocess is still running.

### Utility Functions

**encode_json_line**
- **Signature:** `def encode_json_line(message: dict[str, Any]) -> str`
- Serializes a dict to a compact JSON string with a trailing newline.

**build_error_response**
- **Signature:** `def build_error_response(request_id: int | str, *, code: int, message: str) -> dict[str, Any]`
- Constructs a JSON-RPC error response dict.

## Types

No custom dataclasses — JSON-RPC messages are plain dicts conforming to the JSON-RPC 2.0 spec:

```python
# Request:  {"jsonrpc": "2.0", "id": 1, "method": "...", "params": {...}}
# Response: {"jsonrpc": "2.0", "id": 1, "result": {...}}
# Error:    {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "..."}}
# Notification: {"jsonrpc": "2.0", "method": "...", "params": {...}}
```

## Errors

```python
class JsonRpcError(Exception):
    """Base class for all json_rpc errors."""

class JsonRpcTransportError(JsonRpcError):
    """Transport disconnected or subprocess died."""

class JsonRpcTimeoutError(JsonRpcError):
    """No response within the configured timeout."""

class JsonRpcProtocolError(JsonRpcError):
    """Message violates JSON-RPC 2.0 framing (missing jsonrpc field, unparseable JSON)."""

class JsonRpcErrorResponse(JsonRpcError):
    """Server returned an error response. Fields: code (int), message (str), data (Any | None)."""
```

## State

- **Pending requests:** Internal dict mapping request IDs to asyncio Futures. Populated on `request()`, resolved when the reader loop routes a matching response.
- **Notification queues:** Internal defaultdict of asyncio Queues, keyed by method name. Populated by the reader loop, drained by `next_notification()`.
- **Request ID counter:** Auto-incrementing integer. Not persisted.
- **Reader loop:** Single asyncio Task that reads lines from the transport and routes them.

## Usage Examples

### Basic request-response
```python
from json_rpc import JsonRpcClient, SubprocessTransport

transport = await SubprocessTransport.spawn(["my-server", "--stdio"])
client = JsonRpcClient(transport)
await client.start()

result = await client.request("initialize", {"clientInfo": {"name": "myapp", "version": "1.0"}})
print(result)  # server's initialize response

await client.stop()
```

### Notifications
```python
# Listen for server-pushed status notifications
while True:
    notification = await client.next_notification("status/update", timeout=60.0)
    print(notification["params"]["status"])
```

### Server requests with handler
```python
# Handle server-initiated approval requests
def handle_server_request(message: dict) -> dict:
    method = message["method"]
    if method == "requestApproval":
        return {"decision": "approve"}
    return {"error": {"code": -32601, "message": "Method not found"}}

client.on_server_request(handle_server_request)
```

### Codexbot usage (consumer-side, not in toolkit)
```python
from json_rpc import JsonRpcClient, SubprocessTransport

# codexbot's CodexClient wraps JsonRpcClient
transport = await SubprocessTransport.spawn(
    ["codex", "app-server"],
    cwd="/home/user/workspace",
)
rpc = JsonRpcClient(transport, request_timeout=30.0)
await rpc.start()

# Initialize (generic JSON-RPC)
await rpc.request("initialize", {"clientInfo": {"name": "codexbot", "version": "0.1.0"}})

# Codex-specific thread lifecycle (stays in codexbot, not toolkit)
thread_id = await rpc.request("thread/start", {"cwd": "/path", "model": "gpt-5.4", ...})
```

## Design Notes

### Why stdio / newline-delimited JSON
This is the transport that `codex app-server` uses and that many language-server-protocol (LSP) tools use. It's the simplest subprocess IPC: one JSON object per line, no HTTP overhead, no socket setup. The `JsonRpcTransport` Protocol abstracts this — a WebSocket or TCP transport could implement the same interface.

### What stays in consumers
- **Protocol-specific lifecycle** — Codex threads, turns, streaming, approvals. These are application-level concepts built on top of generic JSON-RPC request/response/notification.
- **Server request policies** — What to approve/deny is the consumer's business logic, not the transport layer's.
- **Subprocess restart strategy** — Whether and how to restart a crashed subprocess is the consumer's decision. The transport reports disconnection; the consumer decides what to do.

### Thread safety
The client is designed for single-event-loop use (standard asyncio pattern). Multiple coroutines can call `request()` and `next_notification()` concurrently on the same client — the reader loop handles routing.

---

## Change History
| Date | What Changed | Why |
|------|-------------|-----|
| 2026-04-20 | Initial ARCH — extracted from codexbot's codex_client.py | Codexbot proved the pattern; extract generic JSON-RPC client for reuse |
