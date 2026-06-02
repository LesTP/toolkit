# Cross-Project Validation Notes

Verification that toolkit ARCH contracts satisfy their known consumers, plus migration notes for TGBot.

## Toolkit ↔ Year-in-Search

Checked against `year-in-search/DESIGN.md`.

| YiS Need | Toolkit Module | Status |
|----------|---------------|--------|
| Embed HN titles (Phase 2) | ARCH_embedding: `embed(texts, config) → EmbeddingResult` | ✅ Direct fit. `all-MiniLM-L6-v2` is the default model. Caching matches YiS's "never re-embed" requirement. |
| HDBSCAN clustering (Phase 3) | ARCH_clustering: `cluster(embeddings, config) → ClusterResult` | ✅ Direct fit. `ClusterStrategy.HDBSCAN` with configurable `min_cluster_size`, `min_samples`, `metric`. UMAP reduction via `reduce_dims` parameter. |
| Optional UMAP before clustering | ARCH_clustering: `reduce_dims` parameter | ✅ Built into ClusterConfig. |
| LLM-assisted labeling (Phase 5) | ARCH_llm_client: `complete(messages, config, tier) → LLMResponse` | ✅ `complete()`, `Message`, `ModelTier` now implemented. YiS does not use llm_client in code today. |
| Telegram delivery | Not needed | — YiS outputs image files, not messages. |

**No gaps found.** The `complete()` API referenced in YiS design is now implemented. YiS doesn't use llm_client in code today, so no runtime impact either way.

**One note:** YiS's DESIGN.md stores embeddings as `.npy` files. Toolkit's ARCH_embedding provides an in-memory `ndarray` result with optional disk cache. YiS can either use toolkit's cache mechanism or save the `result.vectors` ndarray to its own `.npy` file. No conflict — the toolkit returns the vectors, the consumer decides persistence.

## Toolkit ↔ Phosphene

Checked against `phosphene/ARCHITECTURE.md`.

| Phosphene Need | Toolkit Module | Status |
|---------------|---------------|--------|
| Note similarity for link-density | ARCH_embedding: `embed` + `batch_similarity` | ✅ Embed notes, compute similarity against existing note embeddings. |
| RAPTOR-style recursive clustering | ARCH_clustering: `ClusterStrategy.RAPTOR` with `raptor_summarizer` callback | ⚠️ Provisional. Interface defined but untested. Phosphene provides the summarizer (via llm_client). Resolve during distillation implementation. |
| Attention filter LLM calls | ARCH_llm_client: `complete` with `ModelTier.QUALITY` | ✅ `complete()`, `Message`, `ModelTier`, and `TokenUsage` implemented. |
| Multi-provider rotation | ARCH_llm_client: `complete_with_rotation` | ❌ Not implemented. See LLM Client Gap Inventory. |
| Budget tracking | ARCH_llm_client: `get_budget_status` + `BudgetTracker` | ❌ Not implemented. See LLM Client Gap Inventory. |
| Telegram messaging with feedback keyboards | ARCH_telegram_client: `send_message_with_keyboard` | ✅ InlineKeyboard with callback_data covers the like/discuss feedback pattern. |
| Telegraph overflow for long synthesis | ARCH_telegram_client: `publish_telegraph` | ✅ Direct fit for weekly synthesis outputs. |
| Discord messaging | Not in toolkit | ⚠️ Expected. Discord client stays in Phosphene until a second project needs it. Consistent with "second consumer" rule. |
| Embedding for memory store search | ARCH_embedding: `embed` + `batch_similarity(query, candidates, top_k)` | ✅ `top_k` parameter matches retrieval use case. |

**One provisional contract:** RAPTOR clustering strategy requires the consumer to provide a summarizer callback. The interface is defined but the interaction pattern (clustering calls summarizer, which calls llm_client) hasn't been tested in a real pipeline. This is the highest-risk integration point and should be tested early in Phosphene's distillation implementation.

### Modules extracted from Phosphene → Toolkit (2026-06-02)

Three modules were lifted from `phosphene/src/phosphene/` to `toolkit/src/toolkit/`:

| Module | Public API | Phosphene-side change |
|--------|-----------|----------------------|
| `gateway` | Unchanged | Imports rewritten in `generator/generator.py`, `generator/router.py`, `run.py` |
| `source_ingestion` | Unchanged | Imports rewritten in `run.py`, `tools/check_id_collisions{,2}.py`, `tools/check_timestamps.py` |
| `feedback_collector` | Unchanged (now uses internal `_NoteInput` / `_NotePatch` matching Phosphene's `NoteInput` / `NotePatch` field shape, see D-4) | No wiring change — `MemoryStore` accepts the internal note shapes via duck typing |

Phosphene now consumes these as `from toolkit.<module> import ...`. `phosphene/ARCH_<module>.md` files are stubs pointing at the toolkit ARCH equivalents. Test directories moved accordingly: 50 + 69 + 22-of-25 (3 pre-existing datetime failures, see Phosphene `DESIGN_GLOBAL.md`) tests now live in `toolkit/tests/`.

The `feedback_collector` integration test that exercises real Phosphene `Generator` + `MemoryStore` + `FeedbackCollector` wiring stays in `phosphene/tests/feedback_collector/` — it's a Phosphene wiring test, not a toolkit unit test.

## Toolkit ↔ Codexbot

Checked against `codexbot/ARCHITECTURE.md` and implementation source.

| Codexbot Need | Toolkit Module | Status |
|--------------|---------------|--------|
| Long polling for Telegram updates | ARCH_telegram_client: `TelegramClient.start_polling` + `get_next_update` | ✅ Direct fit. Codexbot's `TelegramAdapter` polling loop maps 1:1. |
| Update normalization (command parsing, chat/user extraction) | ARCH_telegram_client: `TelegramClient.normalize_update` → `TelegramUpdate` | ✅ Direct fit. Same dataclass shape as codexbot's `TelegramUpdate`. |
| Send reply messages | ARCH_telegram_client: `TelegramClient.send_message` | ✅ Direct fit. |
| Edit messages (streaming response) | ARCH_telegram_client: `TelegramClient.edit_message` | ✅ Direct fit. Codexbot's streaming-edit UX pattern builds on top. |
| Send inline keyboard (approval buttons) | ARCH_telegram_client: `TelegramClient.send_with_keyboard` | ✅ Direct fit. |
| Message splitting for long responses | ARCH_telegram_client: `split_message` | ✅ Direct fit. Same pure function. |
| Polling offset persistence across restarts | ARCH_telegram_client: `next_update_offset` property | ✅ Exposed for consumer to persist. Codexbot uses its StateStore. |
| JSON-RPC over stdio to Codex app-server | ARCH_json_rpc: `JsonRpcClient` + `SubprocessTransport` | ✅ Direct fit. Generic client handles framing/correlation; Codex-specific protocol stays in codexbot. |
| Request-response correlation with concurrent requests | ARCH_json_rpc: `JsonRpcClient.request` with ID-based routing | ✅ Direct fit. |
| Server notification streaming (agent message deltas) | ARCH_json_rpc: `JsonRpcClient.next_notification` | ✅ Direct fit. Codexbot filters by method name. |
| Server-initiated request handling (approval prompts) | ARCH_json_rpc: `JsonRpcClient.on_server_request` | ✅ Codexbot's `build_default_server_request_response` becomes the handler callback. |
| Subprocess restart on crash | ARCH_json_rpc: `SubprocessTransport.spawn` + consumer-side retry | ✅ The client reports disconnection; codexbot's retry-with-restart logic stays in codexbot. |
| Allowlist enforcement | Not in toolkit | ✅ Correct — security policy is consumer-specific, not transport-level. |
| State persistence (sessions, runs, threads) | Not in toolkit | ✅ Correct — codexbot's StateStore schema is domain-specific. |

**What codexbot keeps after migration:**
- `SecurityLayer` — allowlist/cwd checks (domain-specific policy)
- `CommandRouter` — command classification and dispatch (domain-specific commands)
- `LogReader` — project artifact packaging (domain-specific file layout)
- `StateStore` — SQLite schema for sessions/threads/runs (domain-specific persistence)
- `PatchManager` — diff rendering and approval flow (domain-specific UX)
- `ShellExecutor` — loop-runner subprocess management (could use JSON-RPC transport but overkill for simple exec-and-capture)
- `CodexClient` — Codex-specific protocol layer (threads, turns, approvals) wrapping `JsonRpcClient`
- `main.py` — handler wiring, streaming-edit UX, orchestrator recovery logic

**What codexbot replaces with toolkit imports:**
- `TelegramAdapter` → `toolkit.telegram_client.TelegramClient`
- `HTTPSTelegramTransport` → `toolkit.telegram_client.HTTPSTransport`
- `TelegramUpdate` dataclass → `toolkit.telegram_client.TelegramUpdate`
- `split_message_text()` → `toolkit.telegram_client.split_message()`
- `SubprocessJsonLineTransport` → `toolkit.json_rpc.SubprocessTransport`
- `JsonLineTransport` Protocol → `toolkit.json_rpc.JsonRpcTransport`
- `encode_json_line()` → `toolkit.json_rpc.encode_json_line()`
- Request-ID correlation / reader loop / notification routing → `toolkit.json_rpc.JsonRpcClient`

## LLM Client: ARCH-to-Implementation Gap Inventory

Audit date: 2026-04-28. Compared `ARCH_llm_client.md` (target contract) against `src/toolkit/llm_client/` (implementation). Checked actual usage in all known consumers (TGBot, Codexbot, Year-in-Search).

### Current implementation surface

The implementation provides a **low-level provider abstraction**:
- `LLMConfig(provider, api_key, models, max_tokens, temperature)` — config dataclass
- `LLMProvider.call(model, system_prompt, user_prompt, max_tokens) → LLMResponse` — abstract method
- `AnthropicProvider`, `OpenAIProvider`, `GeminiProvider` — concrete providers
- `create_provider(config) → LLMProvider` — factory
- `LLMResponse(content, model, provider, token_usage: dict)` — response
- `LLMAPIError`, `LLMResponseError` — errors

The ARCH defines a **high-level convenience layer** on top of this. That layer is not implemented.

### Active consumers

| Consumer | Uses llm_client? | Call pattern |
|----------|-----------------|-------------|
| **TGBot** | Yes — via shim `summarization.client` | `create_provider(config).call(model=config.models["quality"], system_prompt=..., user_prompt=..., max_tokens=...)` |
| **Codexbot** | No | Uses `toolkit.json_rpc` only; LLM calls delegated to Codex subprocess |
| **Year-in-Search** | No | Pure data pipeline; LLM labeling described in design doc but not implemented |

TGBot is the only active consumer. It uses the low-level `create_provider().call()` API directly.

### Gap items (priority order)

Items are ordered by when they block Phosphene module implementation.

---

**G-1: `Message` dataclass** — ✅ Complete

Implemented in `types.py`. Dataclass with `role: str` and `content: str`. Exported from `__init__.py`. 29 tests cover it.

---

**G-2: `ModelTier` enum** — ✅ Complete

Implemented in `types.py` as `ModelTier(str, Enum)` with values `QUALITY`, `DEFAULT`, `COMMODITY`. The `str` mixin allows direct use as dict keys (`config.models[ModelTier.QUALITY]`). Exported from `__init__.py`.

---

**G-3: Module-level `complete()` function** — ✅ Complete

Implemented in `providers.py`. Resolves `ModelTier` to model string via `config.models[tier.value]`, splits `list[Message]` into system/user prompts, passes `config.temperature` and `config.max_tokens` through to the provider. Also added `temperature: float = 0.7` parameter to `LLMProvider.call()` ABC and all three provider implementations (Anthropic, OpenAI, Gemini). Exported from `__init__.py`.

---

**G-4: `TokenUsage` dataclass** — ✅ Complete

Implemented in `types.py`. `LLMResponse.token_usage` changed from `dict` to `TokenUsage(input_tokens: int, output_tokens: int)`. All three providers updated. TGBot migrated: `SummaryResult.token_usage` type updated, all dict-style access converted to attribute access, `demo_pipeline.py` `.get()` calls fixed. TGBot test suite passes (37/37).

---

**G-5: `LLMRateLimitError` subclass** — Priority: Nice-to-have, before Orchestrator (Module 10)

ARCH defines `LLMRateLimitError(LLMAPIError)` with `retry_after_seconds`. Implementation folds rate-limit info into the generic `LLMAPIError(retry_after=...)`.

- **What to build:** Subclass in `types.py`. Update providers to raise the subclass on rate-limit responses. ~10 lines.
- **Consumer impact:** Non-breaking. `LLMRateLimitError` inherits from `LLMAPIError`, so existing `except LLMAPIError` catches still work. Consumers that want finer-grained handling can opt in.

---

**G-6: `LLMProviderError`** — Priority: Nice-to-have

ARCH defines `LLMProviderError` for unknown provider names. Implementation raises `ValueError` from `create_provider()`.

- **What to build:** Exception class in `types.py`, update `create_provider()` to raise it. ~5 lines.
- **Consumer impact:** Technically breaking — code catching `ValueError` from `create_provider()` would need updating. In practice, no consumer catches this; provider names are always valid in config files.

---

**G-7: `complete_with_rotation()`** — Priority: Before Orchestrator (Module 10)

ARCH defines `complete_with_rotation(messages, configs: list[LLMConfig], tier) → LLMResponse`. Not implemented. This is Phosphene's subscription rotation strategy — try providers in order, fall through on rate-limit or failure.

- **What to build:** Function that loops over configs, calls `complete()`, catches `LLMAPIError`, tries the next. On full exhaustion, raises `LLMAllProvidersExhaustedError`. ~25 lines.
- **Consumer impact:** Additive. Only Phosphene will use it.
- **Depends on:** G-1, G-2, G-3 (uses `complete()`), G-8 (`LLMAllProvidersExhaustedError`).

---

**G-8: `LLMAllProvidersExhaustedError`** — Priority: With G-7

ARCH defines this error for when all providers in a rotation list fail. Not implemented.

- **What to build:** Exception class in `types.py`. ~5 lines.
- **Consumer impact:** Additive.

---

**G-9: `BudgetTracker` / `BudgetStatus` / `get_budget_status()`** — Priority: Before Orchestrator (Module 10)

ARCH defines a budget tracking interface: `BudgetTracker` (optional field on `LLMConfig`), `BudgetStatus(provider, tokens_used_today, estimated_tokens_remaining, rate_limit_resets_at, status)`, and `get_budget_status(config) → BudgetStatus`. Not implemented. Feeds into Phosphene's ambient stream for budget-aware activation scheduling.

- **What to build:** Types + function + accumulation logic. ~50 lines. Consumer provides storage path; toolkit provides the interface.
- **Consumer impact:** Additive. `BudgetTracker` is an optional field on `LLMConfig` (default `None`), so existing configs are unaffected.

---

**G-10: `OpenRouterProvider`** — Priority: Before Orchestrator (Module 10), possibly deferred further

ARCH lists "openrouter" as a supported provider. Not implemented. OpenRouter uses an OpenAI-compatible API, so `OpenAIProvider` with a different `base_url` may suffice.

- **What to build:** Either a new provider class or a `base_url` parameter on `OpenAIProvider`. ~30 lines.
- **Consumer impact:** Additive. New provider branch in `create_provider()`.

---

### Implementation plan

| Phase | Items | Trigger | TGBot impact |
|-------|-------|---------|-------------|
| ~~**Now** (before Phosphene Seeding)~~ | ~~G-1, G-2, G-3~~ | ~~Blocks Module 2~~ | ~~None (additive)~~ |
| ~~**Now** (optional, recommended)~~ | ~~G-4~~ | ~~Clean up before more consumers depend on the dict~~ | ~~Minor (dict→dataclass for `token_usage`)~~ |
| **Before Module 10** | G-5, G-6, G-7, G-8, G-9, G-10 | Blocks Orchestrator rotation + budget | None (additive) |

**G-1, G-2, G-3, G-4 are complete.** Seeding (Module 2) is unblocked.

### Also noted

- **~~TGBot `demo_pipeline.py` is broken~~** — Fixed. Updated `.get()` dict calls to attribute access on `TokenUsage` dataclass.
- **~~`LLMProvider.call()` lacks `temperature` parameter~~** — Fixed. Added `temperature: float = 0.7` to ABC and all three providers. `complete()` passes `config.temperature` through.

## TGBot Migration Notes

TGBot currently has internal modules that overlap with toolkit. When Phosphene implementation begins, these are candidates for extraction.

### telegram_client.py + formatting.py + telegraph_client.py → toolkit/telegram_client

**Current location:** `TGbot/src/delivery/telegram_client.py`, `formatting.py`, `telegraph_client.py`
**Adaptation needed:**
- `send_digest()` (TGBot's public API) is TGBot-specific — it takes a `Digest` object and handles formatting internally. The toolkit version exposes lower-level primitives: `send_message()`, `send_message_with_keyboard()`, `escape_markdown()`, `publish_telegraph()`.
- TGBot's `formatting.py` contains MarkdownV2 escaping + TGBot-specific layout logic (deep dive formatting, quick hit formatting). The escaping moves to toolkit; the layout logic stays in TGBot.
- TGBot's `send_digest()` would become a thin wrapper that formats a Digest into text, then calls toolkit's `send_message()`.
**Risk:** Low. The Telegram Bot API calls are straightforward. The main work is separating generic escaping/sending from TGBot-specific formatting.

### summarization/client.py → toolkit/llm_client

**Current location:** `TGbot/src/summarization/client.py`
**Adaptation needed:**
- TGBot has `LLMProvider` ABC + `AnthropicProvider` + `create_provider()` factory. This is the starting point for toolkit's provider abstraction.
- TGBot's `LLMConfig` has `provider`, `api_key`, `deep_dive_model`, `quick_hit_model`. Toolkit generalizes to a `models: dict[str, str]` mapping tier names to model identifiers.
- TGBot has no rate-limit tracking or multi-provider rotation. Toolkit adds these.
- TGBot's `generate_deep_dive()` and `generate_quick_hit()` stay in TGBot as domain-specific consumers of toolkit's `complete()`.
**Risk:** Low-medium. The provider abstraction is solid. Adding rotation and budget tracking is new code, not a refactor of existing code.

### No migration needed for:
- **Discovery** — GitHub API client, quality filters. Phosphene doesn't search GitHub.
- **Storage** — SQLite/MySQL CRUD. Phosphene uses Obsidian-compatible markdown files, not a relational DB.
- **Orchestrator** — TGBot-specific pipeline wiring.
