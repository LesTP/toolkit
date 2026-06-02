"""Public Source Ingestion API surface."""

from toolkit.source_ingestion.errors import (
    AdapterConfigError,
    AdapterNotFoundError,
    SourceIngestionError,
)
from toolkit.source_ingestion.ingestion import SourceIngestion
from toolkit.source_ingestion.types import (
    AdapterConfig,
    ContentItem,
    IngestionConfig,
    IngestionError,
    IngestionResult,
)

__all__ = [
    "AdapterConfig",
    "AdapterConfigError",
    "AdapterNotFoundError",
    "ContentItem",
    "IngestionConfig",
    "IngestionError",
    "IngestionResult",
    "SourceIngestion",
    "SourceIngestionError",
]
