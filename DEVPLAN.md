---
phase: 1
phase_title: "Types and core embed function"
step: 6
regime: build
review_done: false
---

# Toolkit — Dev Plan

## Cold Start
Active module: **Embedding** (first in implementation sequence).
Load: ARCH_embedding.md for contract, PROJECT.md for constraints, ARCHITECTURE.md for context.
Consumers waiting: Year-in-Search (Phases 2–3), Phosphene (Seeding, Attention Filter, Distillation, Explorer).

## Current Status
| Module | Status |
|--------|--------|
| Embedding | **In progress** — Phase 1 |
| Clustering | Not started (next after Embedding) |
| LLM Client | Complete |
| Telegram Client | Complete |
| JSON-RPC Client | Complete |

## Phase 1: Types and core embed function

**Regime:** Build
**Scope:** Create types, core embed function with batching and validation, public exports, tests.
**Not in scope:** similarity functions (Phase 2), caching (Phase 3).

### Steps

| Step | What | Test |
|------|------|------|
| 1 | Create `types.py` — all dataclasses and exceptions | Import and instantiate each type |
| 2 | Create `core.py` — `embed()` with model loading, no batching | `embed(["hello"])` returns correct shape and normalized vectors |
| 3 | Add batching to `embed()` | `embed(3 texts, batch_size=2)` matches `embed(3 texts, batch_size=256)` |
| 4 | Add input validation and error paths | Empty list, bad batch_size, bad model name raise correct errors |
| 5 | Create `__init__.py` with public exports | `from toolkit.embedding import embed, EmbeddingConfig, EmbeddingResult` works |
| 6 | Write `tests/embedding/test_core.py` | All tests pass |

### Exit Criteria
- `embed(["hello world"])` → `EmbeddingResult` with shape `(1, 384)`, L2-normalized
- `embed(["a", "b", "c"], EmbeddingConfig(batch_size=2))` batches correctly, shape `(3, 384)`
- `embed([])` raises `EmbeddingInputError`
- `EmbeddingConfig(batch_size=0)` raises `ValueError`
- `EmbeddingConfig(model="nonexistent")` raises `EmbeddingModelError`

## Done Log
| Date | What |
|------|------|
| 2026-04-24 | DEVPLAN.md created. Embedding Phase 1 plan approved. |

---

## Change History
| Date | What Changed | Why |
|------|-------------|-----|
| 2026-04-24 | Initial DEVPLAN.md | Track Embedding module implementation |
| 2026-04-24 | Added frontmatter, rewrote Phase 1 with Build regime steps | Discuss-mode phase planning |
