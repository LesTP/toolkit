# Toolkit — Dev Log

## 2026-04-24 — Embedding Phase 1 complete: Types and core embed function

**Module:** Embedding | **Phase:** 1 | **Regime:** Build | **Result:** All 19 tests passing

### What was built
- `src/toolkit/embedding/types.py` — EmbeddingConfig, EmbeddingResult, EmbeddingModelError, EmbeddingInputError
- `src/toolkit/embedding/core.py` — embed() with batching, L2 normalization, input validation, model caching
- `src/toolkit/embedding/__init__.py` — public API exports
- `tests/embedding/test_core.py` — 19 tests across 4 groups (embed, batching, errors, types)

### Decisions made
- Followed llm_client conventions for types.py layout (section separators, docstrings with Args, Optional from typing)
- Model cache is keyed on (model_name, device) tuple to avoid returning wrong-device model
- `np.asarray(vectors, dtype=np.float32)` kept as defensive cast even though sentence-transformers already returns float32

### Review findings (post-phase)
- **Fixed:** Model cache key was initially model_name only — missed device dimension. Fixed to (model_name, device) tuple.
- **Noted:** ARCH spec says empty strings produce "zero vectors" but sentence-transformers produces non-zero embeddings for "". Spec wording needs update. (Contract Change — see below)

### Contract Change
- ARCH_embedding.md line 11: *"Empty strings are permitted (produce zero vectors)"* should say *"Empty strings are permitted (produce valid vectors)"*. Empty strings do not produce zero vectors in sentence-transformers.

### Not in scope (deferred to later phases)
- similarity() and batch_similarity() — Phase 2
- In-memory LRU cache and disk cache — Phase 3
