"""JSON-RPC error classes."""

from __future__ import annotations


class JsonRpcError(Exception):
    """Base class for JSON-RPC client failures."""


class JsonRpcTransportError(JsonRpcError):
    """Raised when the JSON-RPC transport disconnects."""


class JsonRpcTimeoutError(JsonRpcError):
    """Raised when a JSON-RPC request times out."""


class JsonRpcProtocolError(JsonRpcError):
    """Raised when messages violate the expected JSON-RPC protocol."""


class JsonRpcErrorResponse(JsonRpcError):
    """Raised when the server returns a JSON-RPC error response."""

    def __init__(self, message: str, code: int | None = None, data: object = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data
