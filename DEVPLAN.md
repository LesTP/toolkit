---
module: clustering
phase: 3
phase_title: "RAPTOR recursive clustering"
step: 5
regime: build
review_done: true
---

# Toolkit — Dev Plan

## Cold Start
Active module: **Clustering** (second in implementation sequence).
Load: ARCH_clustering.md for contract, PROJECT.md for constraints, ARCHITECTURE.md for context.
Consumers waiting: Year-in-Search (Phase 3 — HDBSCAN flat clustering), Phosphene (Distillation — RAPTOR recursive clustering).

### Key Context
- **Two strategies:** HDBSCAN (flat, stateless) and RAPTOR (recursive, needs summarizer callback + re-embedding)
- **Dependencies:** `hdbscan`, `umap-learn`, `numpy`
- **RAPTOR needs two callbacks:** `raptor_summarizer` (texts → summary) and `raptor_embedder` (texts → ndarray) — both provided by consumer
- **RAPTOR needs `texts` parameter:** `cluster(embeddings, config, texts=...)` — original texts for summarization
- **Stateless** — no caching, each call is independent

## Current Status
| Module | Status |
|--------|--------|
| Embedding | Complete (43 tests) |
| Clustering | **Complete** — Phase 3 done (48 tests) |
| LLM Client | Complete |
| Telegram Client | Complete |
| JSON-RPC Client | Complete |

## Phase 3: RAPTOR recursive clustering — COMPLETE

**Status:** All steps complete. 48 tests passing (29 original + 19 new RAPTOR tests).
**Contract change:** Added `texts: list[str] | None = None` parameter to `cluster()` — required for RAPTOR, ignored for HDBSCAN.

**Regime:** Build

### Steps

| Step | What | Status |
|------|------|--------|
| 1 | Add `raptor_embedder` to ClusterConfig, update ARCH spec | Done |
| 2 | Implement `_cluster_raptor()` — single recursion level | Done |
| 3 | Multi-level recursion and depth limit | Done |
| 4 | Validation: missing summarizer/embedder/texts → error | Done |
| 5 | Full test suite for RAPTOR | Done (19 new tests) |

### Exit Criteria — All Met
- `cluster(embeddings, ClusterConfig(strategy=RAPTOR, raptor_summarizer=fn, raptor_embedder=fn), texts=texts)` returns tree ✓
- Missing callbacks or texts → ClusterStrategyError ✓
- Texts length mismatch → ClusterInputError ✓
- Recursion stops at max_depth or single cluster ✓
- labels maps original items to leaf-layer clusters ✓
- Original 29 tests unchanged and passing ✓

## Clustering — Completed Phases
- **Phase 1:** Types and HDBSCAN flat clustering — 24 tests. See DEVLOG 2026-04-24.
- **Phase 2:** UMAP dimensionality reduction — 5 new tests (29 total). See DEVLOG 2026-04-24.

## Embedding — Completed Phases
- **Phase 1:** Types and core embed function — 19 tests. See DEVLOG 2026-04-24.
- **Phase 2:** Similarity functions — 12 new tests (31 total). See DEVLOG 2026-04-24.
- **Phase 3:** Caching — 12 new tests (43 total). See DEVLOG 2026-04-24.

---

## Change History
| Date | What Changed | Why |
|------|-------------|-----|
| 2026-04-24 | Initial DEVPLAN.md | Track Embedding module implementation |
| 2026-04-24 | Embedding Phases 1-3 complete | Phase completion protocols |
| 2026-04-24 | Switched active module to Clustering | Cold start for next module |
| 2026-04-24 | Clustering Phase 1 complete | Phase completion protocol |
| 2026-04-24 | Clustering Phase 2 complete | Phase completion protocol |
| 2026-04-24 | Phase 3 plan approved (RAPTOR + raptor_embedder contract change) | Discuss-mode phase planning |
| 2026-04-30 | Phase 3 complete — RAPTOR recursive clustering implemented | 19 new tests (48 total). Added `texts` param to `cluster()`. |
