"""Public Gateway API surface."""

from toolkit.gateway.errors import (
    DeliveryError,
    FormatNotSupportedError,
    GatewayError,
    PlatformConfigError,
    PlatformConnectionError,
    PlatformNotFoundError,
)
from toolkit.gateway.gateway import Gateway
from toolkit.gateway.types import (
    DeliveryResult,
    FeedbackSignal,
    GatewayConfig,
    InboundMessage,
    OutboundMessage,
    PlatformConfig,
)

__all__ = [
    "DeliveryError",
    "DeliveryResult",
    "FeedbackSignal",
    "FormatNotSupportedError",
    "Gateway",
    "GatewayConfig",
    "GatewayError",
    "InboundMessage",
    "OutboundMessage",
    "PlatformConfig",
    "PlatformConfigError",
    "PlatformConnectionError",
    "PlatformNotFoundError",
]
