"""JSON-RPC 2.0 client — public API."""

from .client import JsonRpcClient
from .transport import (
    JsonRpcTransport,
    SubprocessTransport,
    encode_json_line,
)
from .types import (
    JsonRpcError,
    JsonRpcErrorResponse,
    JsonRpcProtocolError,
    JsonRpcTimeoutError,
    JsonRpcTransportError,
)

__all__ = [
    "JsonRpcClient",
    "JsonRpcError",
    "JsonRpcErrorResponse",
    "JsonRpcProtocolError",
    "JsonRpcTimeoutError",
    "JsonRpcTransport",
    "JsonRpcTransportError",
    "SubprocessTransport",
    "WebSocketTransport",
    "encode_json_line",
]


def __getattr__(name: str) -> object:
    if name == "WebSocketTransport":
        from .transport_ws import WebSocketTransport

        globals()["WebSocketTransport"] = WebSocketTransport
        return WebSocketTransport
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
