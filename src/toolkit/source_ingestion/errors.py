"""Source Ingestion exception hierarchy."""


class SourceIngestionError(Exception):
    """Base class for Source Ingestion errors."""


class AdapterConfigError(SourceIngestionError):
    """Raised when an adapter configuration is invalid."""


class AdapterNotFoundError(SourceIngestionError):
    """Raised when an adapter label cannot be found."""
