"""
Core embedding function: text → vector embeddings via sentence-transformers.
"""

import numpy as np
from sentence_transformers import SentenceTransformer

from .types import EmbeddingConfig, EmbeddingInputError, EmbeddingModelError, EmbeddingResult

# Module-level model cache: avoid reloading the same model repeatedly.
_model_cache: dict[tuple[str, str], SentenceTransformer] = {}


def _load_model(model_name: str, device: str) -> SentenceTransformer:
    """Load a sentence-transformers model, caching by (name, device)."""
    key = (model_name, device)
    if key not in _model_cache:
        try:
            _model_cache[key] = SentenceTransformer(model_name, device=device)
        except Exception as exc:
            raise EmbeddingModelError(
                f"Failed to load model '{model_name}': {exc}",
                model=model_name,
            ) from exc
    return _model_cache[key]


def embed(
    texts: list[str],
    config: EmbeddingConfig | None = None,
) -> EmbeddingResult:
    """Embed a list of texts into vectors.

    Args:
        texts: Non-empty list of strings to embed.
        config: Model and batch settings. Uses defaults if None.

    Returns:
        EmbeddingResult with L2-normalized vectors, one per input text.

    Raises:
        EmbeddingInputError: If texts is empty.
        ValueError: If batch_size < 1.
        EmbeddingModelError: If model cannot be loaded.
    """
    if config is None:
        config = EmbeddingConfig()

    if not texts:
        raise EmbeddingInputError("texts must be non-empty")

    if config.batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {config.batch_size}")

    model = _load_model(config.model, config.device)

    vectors = model.encode(
        texts,
        batch_size=config.batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    vectors = np.asarray(vectors, dtype=np.float32)

    return EmbeddingResult(
        vectors=vectors,
        model=config.model,
        dimension=vectors.shape[1],
        from_cache=0,
        computed=len(texts),
    )
