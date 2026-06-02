"""Gateway exception hierarchy."""


class GatewayError(Exception):
    """Base class for Gateway errors."""


class PlatformConfigError(GatewayError):
    """Raised when a platform configuration is invalid."""


class PlatformConnectionError(GatewayError):
    """Raised when a platform listener cannot connect."""


class PlatformNotFoundError(GatewayError):
    """Raised when a target platform is not configured or enabled."""


class FormatNotSupportedError(GatewayError):
    """Raised when a platform does not support the requested output format."""


class DeliveryError(GatewayError):
    """Raised by adapters when a platform delivery API call fails."""
