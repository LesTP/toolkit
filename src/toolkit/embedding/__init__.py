"""
toolkit.embedding — text to vector embeddings.

Public API:
    embed              — text list → EmbeddingResult (vectors + metadata)
    similarity         — cosine similarity between two vectors
    batch_similarity   — rank candidates by similarity to a query
    EmbeddingConfig    — model, batch_size, cache_dir, device
    EmbeddingResult    — vectors (ndarray), model, dimension, cache stats
    EmbeddingModelError — model not found or failed to load
    EmbeddingInputError — input validation failed
"""

from toolkit.embedding.core import batch_similarity, embed, similarity
from toolkit.embedding.types import (
    EmbeddingConfig,
    EmbeddingInputError,
    EmbeddingModelError,
    EmbeddingResult,
)

__all__ = [
    "embed",
    "similarity",
    "batch_similarity",
    "EmbeddingConfig",
    "EmbeddingResult",
    "EmbeddingModelError",
    "EmbeddingInputError",
]
