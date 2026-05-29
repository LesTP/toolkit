# Toolkit — Dev Log

## 2026-05-29 — structured_llm: strip Markdown code fences in parse_json_response

**Module:** structured_llm | **Regime:** Patch | **Result:** 19 tests passing (no regression)

**Contract changes:** `ARCH_structured_llm.md` — `parse_json_response` now strips a single surrounding Markdown code fence (` ```json ... ``` ` or ` ``` ... ``` `) before parsing. Updated "Out of Scope" to clarify that fence stripping IS done but partial extraction from prose is not.

### What was built
- `_strip_code_fences(text)` helper using a `^...$` DOTALL regex that requires the fence to wrap the entire response (rejects "Here is the JSON: { ... }" style outputs).
- `parse_json_response` calls `_strip_code_fences` before `json.loads`.
- No-op for OpenAI responses (which return raw JSON).

### Why
Anthropic (Claude) and Google (Gemini) wrap JSON output in ` ```json ... ``` ` even when the system prompt explicitly requests raw JSON. Before this fix, `structured_call`'s retry loop saw `json.loads` fail silently, retried, hit `max_retries`, and propagated `success=False` with no visible LLM error in the call log. Downstream Diplomat modules received nothing despite the LLM having generated valid (if wrapped) content.

Surfaced during Diplomat's Run 8 multi-provider self-play (3 providers playing the same scenario; before the fix only the OpenAI faction's messages reached the transcript).

### What this is NOT
- No JSON repair (mismatched braces, trailing commas, etc. still fail).
- No partial extraction from prose. Responses like "I propose this: `{...}`" still raise.
- No provider-specific normalization elsewhere. The fence-strip is the only response munging in this layer.

### Verification
- `pytest tests/structured_llm/` — 19 passed.
- Diplomat Run 8 (gpt-4.1-mini + claude-haiku-4-5 + gemini-2.5-flash on the Water Rights scenario) — all three providers now reach the transcript; 11/12 expected messages exchanged (1 lost to a Google free-tier rate limit, unrelated).

---

## 2026-05-17 — Cost Accountant Phase 1 complete

**Module:** Cost Accountant | **Phase:** 1 | **Regime:** Build | **Result:** 28 tests passing
**Contract changes:** ARCH_cost_accountant.md now documents rate-limit detection via `LLMAPIError.status_code == 429` or message match instead of a nonexistent `LLMRateLimitError`.

Built the cost accountant core: typed budgets/estimates/reports, model pricing,
JSONL ledger creation/load/append, cost estimation, budget-enforced
`complete()` wrapping `llm_client`, hard aborts for rate limits and spending
caps, historical reporting with anomalies, session totals, public exports, and
the cost accountant test suite. Verified with
`PYTHONPATH=/home/claude/workspace/toolkit/src /home/claude/toolkit-venv/bin/python3 -m pytest tests/cost_accountant/`
(`28 passed`).

---

## 2026-04-30 — Clustering Phase 3 complete: RAPTOR recursive clustering

**Module:** Clustering | **Phase:** 3 | **Regime:** Build | **Result:** 48 tests passing (19 new)

### What was built
- `_cluster_raptor()` in core.py — cluster → summarize → embed → recurse, building a tree of ClusterLayer objects
- Added `texts: list[str] | None = None` parameter to `cluster()` — required for RAPTOR (summarizer needs original texts), ignored for HDBSCAN
- Validation: missing `raptor_summarizer`, `raptor_embedder`, or `texts` → ClusterStrategyError; texts length mismatch → ClusterInputError
- Recursion stops at `raptor_max_depth` or when ≤1 cluster remains
- Labels in ClusterResult come from the leaf level; tree spans depth 0 (leaf) to root

### Decisions made
- `texts` as a `cluster()` parameter rather than on ClusterConfig — data belongs in the function call, not configuration
- Recursive HDBSCAN calls use `reduce_dims=None` (via `dataclasses.replace`) — summary embeddings may have fewer dims than the original `reduce_dims` value, which would crash UMAP
- Summarizer called per-cluster (one cluster's texts at a time); embedder called per-batch (all summaries at once) — matches expected consumer patterns

### Review findings (post-phase)
- **Fixed:** `reduce_dims` inherited by recursive HDBSCAN calls — would crash if summary embeddings had fewer dims than `reduce_dims`. Fixed with `replace(config, reduce_dims=None)`.
- **Fixed:** Dead variable `summary_cluster_ids` — populated but never read. Removed.
- **Fixed:** Dead variable `current_embeddings` — reassigned in loop but never read after initial use. Removed.
- **Fixed:** ARCH usage example missing `texts` parameter — would fail at runtime. Added `texts=titles`.

### Contract Change
- `cluster()` signature: added `texts: list[str] | None = None` as third parameter. ARCH_clustering.md updated (signature, errors, usage example).

---

## 2026-04-24 — Clustering Phase 2 complete: UMAP dimensionality reduction

**Module:** Clustering | **Phase:** 2 | **Regime:** Build | **Result:** 29 tests passing (5 new)

### What was built
- Optional UMAP reduction in `_cluster_hdbscan` — when `reduce_dims` is set, reduces embeddings before clustering
- Lazy import of `umap` (only loaded when reduction is requested)
- `random_state=42` for deterministic reduction

### Decisions made
- UMAP uses fixed defaults (n_neighbors, min_dist) — ARCH spec only exposes `reduce_dims`
- `random_state=42` ensures reproducibility at cost of a harmless warning

### Review findings (post-phase)
- Clean phase. No issues found.

---

## 2026-04-24 — Clustering Phase 1 complete: Types and HDBSCAN flat clustering

**Module:** Clustering | **Phase:** 1 | **Regime:** Build | **Result:** 24 tests passing

### What was built
- `types.py` — ClusterConfig, ClusterResult, ClusterStrategy enum, ClusterLayer, ClusterInputError, ClusterStrategyError
- `core.py` — `cluster()` function with HDBSCAN strategy via lazy `import hdbscan`
- `__init__.py` — public exports for all types and the cluster function
- RAPTOR strategy raises ClusterStrategyError (not yet implemented)
- `reduce_dims` silently ignored (UMAP deferred to Phase 2)

### Decisions made
- Lazy import for hdbscan (inside `_cluster_hdbscan`) — avoids import cost when module is loaded but not used
- Plain `set(labels) - {-1}` for cluster counting — simple, correct for HDBSCAN output
- All RAPTOR-related types defined now (ClusterLayer, tree field) but only populated in Phase 3

### Review findings (post-phase)
- **Fixed:** Removed unused `field` import from types.py
- Defensive "unknown strategy" branch in core.py is unreachable but kept as guard

---

## 2026-04-24 — Embedding Phase 3 complete: Caching

**Module:** Embedding | **Phase:** 3 | **Regime:** Build | **Result:** 43 tests passing (12 new)

### What was built
- In-memory embedding cache: plain dict keyed on `(model, text_hash)`, avoids re-encoding already-seen texts
- Disk cache: when `cache_dir` is set, saves/loads vectors as `.npy` files in `cache_dir/model_name/hash.npy`
- `from_cache` and `computed` counts now reflect actual cache behavior (mixed hits handled correctly)
- SHA-256 text hashing for stable, collision-resistant cache keys

### Decisions made
- Plain dict (unlimited) instead of LRU — spec says "bounded by available memory", no eviction needed
- Disk cache stored as individual `.npy` files per vector (simple, no index file needed)
- Corrupt `.npy` files silently re-computed (cache is best-effort, re-computing is always safe)
- Model name used as subdirectory (with `/` replaced by `_`) for disk isolation

### Review findings (post-phase)
- **Fixed:** Added `setup_method` to TestEmbed for cache isolation — module-level cache could cause test order dependencies
- No correctness issues, no architecture drift

---

## 2026-04-24 — Embedding Phase 2 complete: Similarity functions

**Module:** Embedding | **Phase:** 2 | **Regime:** Build | **Result:** 31 tests passing (12 new)

### What was built
- `similarity(a, b) -> float` — cosine similarity via dot product (assumes L2-normalized inputs)
- `batch_similarity(query, candidates, top_k) -> list[tuple[int, float]]` — ranked similarity search via matrix multiply + argsort
- Updated `__init__.py` exports and docstring
- 12 new tests: TestSimilarity (6), TestBatchSimilarity (6)

### Decisions made
- Pure numpy implementation — no additional dependencies needed
- `similarity()` uses `np.dot` directly since embed() guarantees L2 normalization
- `batch_similarity()` uses `candidates @ query` for vectorized computation

### Review findings (post-phase)
- Clean phase. No correctness issues, no dead code, no architecture drift.

---

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

---

## 2026-05-28 — Prompt Regression Phase 2 planned

**Module:** Prompt Regression | **Phase:** 2 | **Regime:** Build | **Result:** plan moved to execution

Registered Prompt Regression in the toolkit architecture and corrected the
active DEVPLAN context for extraction from diplomat. The phase will extract
generic scenario types, JSON path helpers, LLM judging, and runner/reporting
logic into `toolkit.prompt_regression`, while diplomat keeps the
domain-specific module dispatch through a `module_caller` callback.

### Step 2.1: Prompt Regression architecture contract
Mode: Build
Outcome: Complete
Contract changes: Added `ARCH_prompt_regression.md`; ARCHITECTURE.md already lists Prompt Regression from phase planning.

Created the prompt regression module contract before implementation. The ARCH
defines scenario loading, JSON path helpers, dataclass outputs, `LLMJudge`, and
`ScenarioRunner` with consumer-provided `module_caller` dispatch. It also
documents that the judge uses an injected `complete(messages, config, tier)`
client protocol rather than importing `toolkit.llm_client`.

---

## 2026-05-28 — Structured LLM Phase 3 planned

**Module:** Structured LLM | **Phase:** 3 | **Regime:** Build | **Result:** plan moved to execution

Registered Structured LLM in the toolkit architecture and moved the phase into
execution. The phase will extract diplomat's repeated LLM completion, JSON
parsing, JSON Schema validation, and prompt/schema loading helpers into a leaf
`toolkit.structured_llm` module with an injected client protocol.

### Step 3.1: Structured LLM architecture contract
Mode: Build
Outcome: Complete
Contract changes: Added `ARCH_structured_llm.md`; ARCHITECTURE.md lists Structured LLM as an in-progress leaf module.

Created the structured LLM module contract before implementation. The ARCH
defines `structured_complete`, `parse_json_response`, `validate_json_schema`,
`load_prompt`, and `load_schema`, and documents that LLM access is injected via
the `complete(messages, config, tier)` protocol instead of importing
`toolkit.llm_client`.

### Step 3.2: Structured LLM module implementation
Mode: Build
Outcome: Complete
Contract changes: Added `toolkit.structured_llm` public API and declared `jsonschema` as a runtime dependency.

Implemented `structured_complete`, `parse_json_response`,
`validate_json_schema`, `load_prompt`, and `load_schema` in
`src/toolkit/structured_llm/`. Added 13 unit tests covering JSON parsing,
schema validation path/label formatting, file loaders, sync and async fake LLM
clients, and non-text response rejection.

Verification:
- `tests/structured_llm/`: 13 passed
- `tests/test_prompt_regression.py`: 26 passed
- `tests/cost_accountant/`: 28 passed
- `tests/llm_client/`: 29 passed

Full `pytest` was not usable in this environment: `jsonschema` had to be
installed into a temporary local target because the shared venv is not
writable, `numpy` is absent for embedding/clustering, and collecting all test
directories together hits existing duplicate `test_core.py` module-name
collisions. The temporary dependency target was removed after verification.
