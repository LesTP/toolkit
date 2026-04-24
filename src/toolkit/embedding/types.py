"""
Embedding types: configuration, result, and error classes.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class EmbeddingConfig:
    """Configuration for the embedding module.

    Args:
        model: sentence-transformers model name.
        batch_size: Texts per batch (memory/speed tradeoff). Must be >= 1.
        cache_dir: Disk cache directory. None = no disk cache.
        device: Compute device ("cpu" or "cuda").
    """

    model: str = "all-MiniLM-L6-v2"
    batch_size: int = 256
    cache_dir: Optional[str] = None
    device: str = "cpu"


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class EmbeddingResult:
    """Result of an embed() call.

    Guarantees:
        - vectors.shape[0] == number of input texts (same order)
        - vectors.shape[1] == dimension
        - Vectors are L2-normalized (unit length)
    """

    vectors: np.ndarray  # shape (n_texts, embedding_dim)
    model: str  # model identifier used
    dimension: int  # embedding dimensionality (e.g. 384)
    from_cache: int  # count of texts served from cache
    computed: int  # count of texts freshly computed


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class EmbeddingModelError(Exception):
    """Model not found or failed to load."""

    def __init__(self, message: str, model: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.model = model


class EmbeddingInputError(Exception):
    """Input validation failed (e.g. empty texts list)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
