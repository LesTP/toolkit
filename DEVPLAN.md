---
module: clustering
phase: 3
phase_title: "RAPTOR recursive clustering"
step: 2
regime: build
review_done: false
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
- **Stateless** — no caching, each call is independent

## Current Status
| Module | Status |
|--------|--------|
| Embedding | Complete (43 tests) |
| Clustering | **In progress** — Phase 3 |
| LLM Client | Complete |
| Telegram Client | Complete |
| JSON-RPC Client | Complete |

## Phase 3: RAPTOR recursive clustering

**Regime:** Build
**Scope:** Implement RAPTOR strategy (cluster → summarize → embed → recurse), populate ClusterResult.tree, validate RAPTOR callbacks.
**Contract change:** Add `raptor_embedder: Callable | None = None` to ClusterConfig and ARCH spec.

### Steps

| Step | What | Test |
|------|------|------|
| 1 | Add `raptor_embedder` to ClusterConfig, update ARCH spec | Config change, spec updated |
| 2 | Implement `_cluster_raptor()` — single recursion level | Synthetic data + mock callbacks → tree with depth 0 and 1 |
| 3 | Multi-level recursion and depth limit | raptor_max_depth=2 → stops at depth 2, raptor_max_depth=1 → single level |
| 4 | Validation: missing summarizer/embedder → error | ClusterStrategyError for missing callbacks |
| 5 | Full test suite for RAPTOR | All tests passing |

### Exit Criteria
- `cluster(embeddings, ClusterConfig(strategy=RAPTOR, raptor_summarizer=fn, raptor_embedder=fn))` returns tree
- Missing callbacks → ClusterStrategyError
- Recursion stops at max_depth or single cluster
- labels maps original items to leaf-layer clusters
- Existing 29 tests unchanged

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
