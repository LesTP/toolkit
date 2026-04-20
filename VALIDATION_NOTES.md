# Cross-Project Validation Notes

Verification that toolkit ARCH contracts satisfy their known consumers, plus migration notes for TGBot.

## Toolkit ↔ Year-in-Search

Checked against `year-in-search/DESIGN.md`.

| YiS Need | Toolkit Module | Status |
|----------|---------------|--------|
| Embed HN titles (Phase 2) | ARCH_embedding: `embed(texts, config) → EmbeddingResult` | ✅ Direct fit. `all-MiniLM-L6-v2` is the default model. Caching matches YiS's "never re-embed" requirement. |
| HDBSCAN clustering (Phase 3) | ARCH_clustering: `cluster(embeddings, config) → ClusterResult` | ✅ Direct fit. `ClusterStrategy.HDBSCAN` with configurable `min_cluster_size`, `min_samples`, `metric`. UMAP reduction via `reduce_dims` parameter. |
| Optional UMAP before clustering | ARCH_clustering: `reduce_dims` parameter | ✅ Built into ClusterConfig. |
| LLM-assisted labeling (Phase 5) | ARCH_llm_client: `complete(messages, config, tier) → LLMResponse` | ✅ Simple single-provider call. YiS uses `ModelTier.COMMODITY` for label cleanup. |
| Telegram delivery | Not needed | — YiS outputs image files, not messages. |

**No gaps found.** Year-in-Search can consume embedding, clustering, and llm_client as-is.

**One note:** YiS's DESIGN.md stores embeddings as `.npy` files. Toolkit's ARCH_embedding provides an in-memory `ndarray` result with optional disk cache. YiS can either use toolkit's cache mechanism or save the `result.vectors` ndarray to its own `.npy` file. No conflict — the toolkit returns the vectors, the consumer decides persistence.

## Toolkit ↔ Phosphene

Checked against `phosphene/ARCHITECTURE.md`.

| Phosphene Need | Toolkit Module | Status |
|---------------|---------------|--------|
| Note similarity for link-density | ARCH_embedding: `embed` + `batch_similarity` | ✅ Embed notes, compute similarity against existing note embeddings. |
| RAPTOR-style recursive clustering | ARCH_clustering: `ClusterStrategy.RAPTOR` with `raptor_summarizer` callback | ⚠️ Provisional. Interface defined but untested. Phosphene provides the summarizer (via llm_client). Resolve during distillation implementation. |
| Attention filter LLM calls | ARCH_llm_client: `complete` with `ModelTier.QUALITY` | ✅ Direct fit. |
| Multi-provider rotation | ARCH_llm_client: `complete_with_rotation` | ✅ Designed for Phosphene's subscription rotation strategy. |
| Budget tracking | ARCH_llm_client: `get_budget_status` + `BudgetTracker` | ✅ Feeds into Phosphene's ambient stream (budget awareness). |
| Telegram messaging with feedback keyboards | ARCH_telegram_client: `send_message_with_keyboard` | ✅ InlineKeyboard with callback_data covers the like/discuss feedback pattern. |
| Telegraph overflow for long synthesis | ARCH_telegram_client: `publish_telegraph` | ✅ Direct fit for weekly synthesis outputs. |
| Discord messaging | Not in toolkit | ⚠️ Expected. Discord client stays in Phosphene until a second project needs it. Consistent with "second consumer" rule. |
| Embedding for memory store search | ARCH_embedding: `embed` + `batch_similarity(query, candidates, top_k)` | ✅ `top_k` parameter matches retrieval use case. |

**One provisional contract:** RAPTOR clustering strategy requires the consumer to provide a summarizer callback. The interface is defined but the interaction pattern (clustering calls summarizer, which calls llm_client) hasn't been tested in a real pipeline. This is the highest-risk integration point and should be tested early in Phosphene's distillation implementation.

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
