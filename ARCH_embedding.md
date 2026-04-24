# ARCH: Embedding

## Purpose
Convert text into vector embeddings for downstream similarity computation, clustering, and retrieval. Model-agnostic — consumers specify which model to use. Handles batching and caching internally.

## Public API

### embed
- **Signature:** `embed(texts: list[str], config: EmbeddingConfig | None = None) -> EmbeddingResult`
- **Parameters:**
  - texts: list[str] — input texts to embed. Must be non-empty. Empty strings are permitted (produce valid vectors).
  - config: EmbeddingConfig | None — model and cache settings. If None, uses defaults.
    ```python
    @dataclass
    class EmbeddingConfig:
        model: str = "all-MiniLM-L6-v2"   # sentence-transformers model name
        batch_size: int = 256               # texts per batch (memory/speed tradeoff)
        cache_dir: str | None = None        # disk cache directory. None = no disk cache
        device: str = "cpu"                 # "cpu" or "cuda"
    ```
- **Returns:** EmbeddingResult
- **Errors:**
  - `EmbeddingModelError` — model not found or failed to load. Includes model name.
  - `EmbeddingInputError` — texts list is empty.
  - `ValueError` — batch_size < 1.

### similarity
- **Signature:** `similarity(a: ndarray, b: ndarray) -> float`
- **Parameters:**
  - a: ndarray — single embedding vector (1-D)
  - b: ndarray — single embedding vector (1-D), same dimensionality as a
- **Returns:** float — cosine similarity in [-1, 1]
- **Errors:**
  - `ValueError` — dimension mismatch between a and b

### batch_similarity
- **Signature:** `batch_similarity(query: ndarray, candidates: ndarray, top_k: int | None = None) -> list[tuple[int, float]]`
- **Parameters:**
  - query: ndarray — single embedding vector (1-D)
  - candidates: ndarray — matrix of embeddings (2-D, each row is a vector)
  - top_k: int | None — return only the top K results. None = return all, sorted by similarity descending.
- **Returns:** list of (index, similarity_score) tuples, sorted by similarity descending
- **Errors:**
  - `ValueError` — dimension mismatch between query and candidate vectors

## Inputs
- List of strings (any length, any language — model determines quality)
- EmbeddingConfig specifying model, batch size, cache behavior

## Outputs
- **EmbeddingResult:**
  ```python
  @dataclass
  class EmbeddingResult:
      vectors: ndarray          # shape (n_texts, embedding_dim)
      model: str                # model identifier used
      dimension: int            # embedding dimensionality (e.g. 384)
      from_cache: int           # count of texts served from cache
      computed: int             # count of texts freshly computed
  ```
- Guarantees:
  - `vectors.shape[0] == len(texts)` — one vector per input text, same order
  - `vectors.shape[1] == dimension` — consistent dimensionality
  - Vectors are L2-normalized (unit length) — cosine similarity reduces to dot product
  - Deterministic: same model + same text = same vector (enables caching)

## State
- **In-memory cache:** LRU cache keyed on `(model, text_hash)`. Survives within a process. Size bounded by available memory.
- **Disk cache (optional):** If `cache_dir` is set, embeddings are persisted to disk as numpy arrays keyed on `(model, text_hash)`. Survives across processes and restarts. Consumer manages cache directory lifecycle (cleanup, size limits).
- Cache invalidation: none. Embeddings are deterministic for a given model+text pair. Switching models naturally uses different cache keys.

## Usage Example
```python
from embedding import embed, similarity, EmbeddingConfig

config = EmbeddingConfig(model="all-MiniLM-L6-v2", cache_dir="./cache/embeddings")

result = embed(["autonomous agent memory", "Zettelkasten slip box"], config)
print(f"Dimension: {result.dimension}, cached: {result.from_cache}")

score = similarity(result.vectors[0], result.vectors[1])
print(f"Similarity: {score:.3f}")
```
