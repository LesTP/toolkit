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
    "encode_json_line",
]
