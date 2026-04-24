"""
Core embedding function: text → vector embeddings via sentence-transformers.
"""

import hashlib
import os

import numpy as np
from sentence_transformers import SentenceTransformer

from .types import EmbeddingConfig, EmbeddingInputError, EmbeddingModelError, EmbeddingResult

# Module-level model cache: avoid reloading the same model repeatedly.
_model_cache: dict[tuple[str, str], SentenceTransformer] = {}

# Module-level embedding cache: (model, text_hash) → vector.
_embedding_cache: dict[tuple[str, str], np.ndarray] = {}


def _text_hash(text: str) -> str:
    """Stable hash for cache key."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _disk_cache_path(cache_dir: str, model: str, text_h: str) -> str:
    """Return file path for a cached embedding vector."""
    model_dir = os.path.join(cache_dir, model.replace("/", "_"))
    return os.path.join(model_dir, f"{text_h}.npy")


def _load_from_disk(path: str) -> np.ndarray | None:
    """Load a cached vector from disk, or None if missing/corrupt."""
    if os.path.exists(path):
        try:
            return np.load(path)
        except Exception:
            return None
    return None


def _save_to_disk(path: str, vector: np.ndarray) -> None:
    """Save a vector to disk cache."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.save(path, vector)


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

    # Check in-memory cache, then disk cache, for each text.
    hashes = [_text_hash(t) for t in texts]
    cached_vectors: dict[int, np.ndarray] = {}
    texts_to_compute: list[tuple[int, str]] = []

    for i, (text, h) in enumerate(zip(texts, hashes)):
        cache_key = (config.model, h)
        if cache_key in _embedding_cache:
            cached_vectors[i] = _embedding_cache[cache_key]
        elif config.cache_dir is not None:
            disk_vec = _load_from_disk(
                _disk_cache_path(config.cache_dir, config.model, h)
            )
            if disk_vec is not None:
                cached_vectors[i] = disk_vec
                _embedding_cache[cache_key] = disk_vec
            else:
                texts_to_compute.append((i, text))
        else:
            texts_to_compute.append((i, text))

    # Compute only the missing embeddings.
    if texts_to_compute:
        model = _load_model(config.model, config.device)
        new_texts = [t for _, t in texts_to_compute]
        new_vectors = model.encode(
            new_texts,
            batch_size=config.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        new_vectors = np.asarray(new_vectors, dtype=np.float32)

        for j, (i, _) in enumerate(texts_to_compute):
            vec = new_vectors[j]
            cached_vectors[i] = vec
            _embedding_cache[(config.model, hashes[i])] = vec
            if config.cache_dir is not None:
                _save_to_disk(
                    _disk_cache_path(config.cache_dir, config.model, hashes[i]),
                    vec,
                )

    # Assemble result in original order.
    vectors = np.stack([cached_vectors[i] for i in range(len(texts))])

    return EmbeddingResult(
        vectors=vectors,
        model=config.model,
        dimension=vectors.shape[1],
        from_cache=len(texts) - len(texts_to_compute),
        computed=len(texts_to_compute),
    )


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two embedding vectors.

    Args:
        a: Single embedding vector (1-D).
        b: Single embedding vector (1-D), same dimensionality as a.

    Returns:
        Cosine similarity in [-1, 1].

    Raises:
        ValueError: If a and b have different dimensions.
    """
    if a.shape != b.shape:
        raise ValueError(
            f"Dimension mismatch: a has shape {a.shape}, b has shape {b.shape}"
        )
    return float(np.dot(a, b))


def batch_similarity(
    query: np.ndarray,
    candidates: np.ndarray,
    top_k: int | None = None,
) -> list[tuple[int, float]]:
    """Rank candidates by cosine similarity to a query vector.

    Args:
        query: Single embedding vector (1-D).
        candidates: Matrix of embeddings (2-D, each row is a vector).
        top_k: Return only the top K results. None = return all.

    Returns:
        List of (index, similarity_score) tuples, sorted descending.

    Raises:
        ValueError: If query and candidate dimensions don't match.
    """
    if query.shape[0] != candidates.shape[1]:
        raise ValueError(
            f"Dimension mismatch: query has {query.shape[0]} dims, "
            f"candidates have {candidates.shape[1]} dims"
        )
    scores = candidates @ query
    indices = np.argsort(scores)[::-1]
    if top_k is not None:
        indices = indices[:top_k]
    return [(int(i), float(scores[i])) for i in indices]
