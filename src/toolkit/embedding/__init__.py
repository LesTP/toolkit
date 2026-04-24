"""
toolkit.embedding — text to vector embeddings.

Public API:
    embed              — text list → EmbeddingResult (vectors + metadata)
    EmbeddingConfig    — model, batch_size, cache_dir, device
    EmbeddingResult    — vectors (ndarray), model, dimension, cache stats
    EmbeddingModelError — model not found or failed to load
    EmbeddingInputError — input validation failed
"""

from toolkit.embedding.core import embed
from toolkit.embedding.types import (
    EmbeddingConfig,
    EmbeddingInputError,
    EmbeddingModelError,
    EmbeddingResult,
)

__all__ = [
    "embed",
    "EmbeddingConfig",
    "EmbeddingResult",
    "EmbeddingModelError",
    "EmbeddingInputError",
]
