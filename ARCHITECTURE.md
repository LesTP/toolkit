# Toolkit — Architecture

## Component Map

| Component | Responsibility | Dependencies | Provenance |
|-----------|---------------|--------------|------------|
| Embedding | Text → vector embeddings. Batch encoding, caching, configurable model. | none (leaf) | New |
| Clustering | Semantic grouping over embeddings. Pluggable strategies (HDBSCAN, RAPTOR-style recursive). | none (leaf) | New |
| LLM Client | Provider-agnostic LLM API. Model tiers, rate-limit tracking, multi-provider rotation. | none (leaf) | Adapted from TGBot summarization/client.py |
| Telegram Client | Telegram Bot API: send messages, receive updates (long polling), edit messages, MarkdownV2 formatting, inline keyboards, message splitting, Telegraph overflow. | none (leaf) | Sending adapted from TGBot delivery/; receiving adapted from codexbot telegram_adapter |
| JSON-RPC Client | Async JSON-RPC 2.0 client over stdio. Request-response correlation, notification routing, subprocess transport. | none (leaf) | Extracted from codexbot codex_client.py |
| Cost Accountant | Cost tracking and budget enforcement for LLM API calls. Wraps llm_client with pre-call estimation, budget checking, append-only ledger, rate-limit abort, and reporting. | LLM Client | New — motivated by Phosphene cost incidents |
| Prompt Regression | Reusable prompt regression test framework: scenario loading, JSON path property checks, LLM judging, and run reporting with consumer-provided module dispatch. | none (leaf; injected LLM client protocol) | Extracted from diplomat tests/prompt_regression |
| Structured LLM | Reusable call LLM, parse JSON, and validate schema helpers with an injected LLM client protocol. | none (leaf; injected LLM client protocol) | Extracted from diplomat modules |
| Gateway | Multi-platform message bus (inbound + outbound). Adapter registry with Telegram (via toolkit/telegram_client), log, and fake adapters. Feedback signal dispatch (reactions/replies/edits). | toolkit/telegram_client (optional, for telegram adapter) | Extracted from Phosphene 2026-06 |
| Source Ingestion | Adapter framework for pulling content into a uniform `ContentItem`. Concrete adapters: RSS, Telegram channel, Reddit, human-share DM, corpus importers (LiveJournal, Blogspot, plain text, Facebook). Durable last-seen markers. URL fetching with normalization. | none (leaf) | Extracted from Phosphene 2026-06 |
| Feedback Collector | Normalises platform feedback signals (reactions, replies, silence, forwards) into structured `FeedbackEvent`s written to a memory store. Output tracking, bounded pruning, silence detection. Memory store contract is duck-typed (see ARCH_feedback_collector.md). | (consumer-supplied memory store; structural contract only) | Extracted from Phosphene 2026-06 |
| Coaching | Tag-based operator-input parser. Reads `TAG: content` notes into typed `CoachingEvent` (routed to a consumer-defined queue with a canonical type) and `/command args` into typed `Command` objects. Tag vocabulary and command list loaded from YAML or pre-parsed dict. PyYAML lazy-imported in the file loader only. | none (leaf) | Extracted from Diplomat 2026-06-05; Clanker Courts queued as second consumer |
| Edit Classifier | LLM-as-judge categorical classifier for review-gate edit logs. Takes `(original, edited, edit_notes)` and returns a typed `EditClassification` with category (one of six: tone_softer, tone_harder, commitment_removed, ambiguity_added, constraint_enforcement, persona_correction), confidence, rationale, classifier model, tz-aware timestamp. Project-side `build_*` factory pattern. | toolkit/structured_llm (one-way; the LLM client itself is injected through `structured_call`'s first argument) | Extracted from Diplomat 2026-06-07; Clanker Courts queued as second consumer |
| Clankmates Client | Subprocess wrapper around the `clankm` CLI for Clankmates messaging. Player-side ops: `whoami`, `list_threads`, `show_thread`, `archive_thread`, `send`, `reply`. Message decoders (`decode.py`), thread-cursor persistence (`cursor.py`), peer-DM screening rules (`screen.py`). | none (leaf) | Vendored from clanker-courts-player-client 2026-06-10; consumers: Diplomat (arena), Clanker Courts (game_transport adapter) |

## Data Flow

### Core Objects
- **EmbeddingResult** — ndarray of vectors + model identifier + input hash (for cache validation)
- **ClusterResult** — cluster assignments (int array), cluster count, noise label count, strategy used
- **LLMResponse** — content (str), model used, token usage (input/output counts), provider name
- **SendResult** — success (bool), message_id (int|None), error (str|None)
- **TelegramUpdate** — chat_id, user_id, message_text, command, args, message_id, raw
- **Prompt Regression RunReport** — scenario results, property outcomes, judge verdicts, and summary counts
- **Structured LLM JSON object** — parsed dict response validated against a caller-provided JSON Schema

### Flow
No data flows between toolkit modules. Each is a leaf consumed independently by application projects. Application projects wire them together:

```
Year-in-Search:  HN titles → Embedding → Clustering → (labels via LLM Client)
Phosphene:       Source content → Embedding → Memory Store ← Clustering ← Distillation (via LLM Client)
                 Generator output → Telegram Client / Discord
TGBot:           Repo content → LLM Client → Telegram Client
Codexbot:        Telegram updates → Telegram Client (polling) → Command Router
                 Model queries → JSON-RPC Client → Codex app-server
Diplomat:        Prompt scenarios → Prompt Regression → diplomat module callbacks → reports
                 Domain prompts → Structured LLM → validated JSON → domain result types
```

## Implementation Sequence

| Order | Module | Rationale | Status |
|-------|--------|-----------|--------|
| 1 | Embedding | Leaf, simplest module. Year-in-Search needs it first. | Complete |
| 2 | Clustering | Leaf, depends on Embedding outputs conceptually but not as a code dependency. Year-in-Search needs both. | Complete |
| 3 | LLM Client | Leaf, more complex (multi-provider, rate limits). Builds on TGBot's tested AnthropicProvider. | Complete |
| 4 | Telegram Client | Leaf. Sending side working in TGBot, receiving side working in codexbot. Merge rather than new build. | Complete |
| 5 | JSON-RPC Client | Leaf. Working in codexbot. Extract if second consumer materializes. | Complete |
| 6 | Cost Accountant | Wraps LLM Client. Budget enforcement, cost ledger, rate-limit abort. Prerequisite for Phosphene LLM resume. | Complete |
| 7 | Prompt Regression | Leaf test framework extracted from diplomat so prompt behavior checks can be reused by Diplomat and Phosphene. | Complete |
| 8 | Structured LLM | Leaf helper module for repeated LLM JSON extraction and schema validation patterns shared across Diplomat and future consumers. | Complete |
| 9 | Gateway | Multi-platform message bus extracted from Phosphene. Telegram + log + fake adapters; inbound + outbound; feedback signal dispatch. | Complete — extracted 2026-06 |
| 10 | Source Ingestion | Adapter framework + RSS/Telegram channel/Reddit/human-share/corpus importers extracted from Phosphene. | Complete — extracted 2026-06 |
| 11 | Feedback Collector | Platform signal normalisation extracted from Phosphene. Memory store contract is duck-typed (no toolkit-cross-import). | Complete — extracted 2026-06 |
| 12 | Coaching | Tag-based operator-input parser extracted from Diplomat. YAML config (lazy-imported) or pre-parsed dict. Clanker Courts incoming as second consumer. | Complete — extracted 2026-06-05 |
| 13 | Edit Classifier | LLM-as-judge categorical classifier extracted from Diplomat. Six-category enum (project-side factory + prompt). Clanker Courts incoming as second consumer. | Complete — extracted 2026-06-07 |
| 14 | Clankmates Client | Subprocess wrapper + message decoders + cursor store + peer-DM screener. Vendored from clanker-courts-player-client; extended for toolkit reuse. Consumers: Diplomat (arena), Clanker Courts. | In progress |

## Coupling Notes

- **No cross-dependencies** (with three documented exceptions). Toolkit modules never import from each other — except:
  1. **Cost Accountant** wraps **LLM Client** (one-way, optional).
  2. **Gateway**'s telegram adapter optionally imports **toolkit.telegram_client** (one-way, optional; gateway works without it for log/fake adapters and accepts a consumer-supplied telegram client factory).
  3. **Edit Classifier** calls **toolkit.structured_llm.structured_call** (one-way; the LLM client itself is injected through `structured_call`'s first argument, preserving the no-direct-llm_client-import rule).
  Consumers that don't need cost tracking use LLM Client directly. Consumers that don't need Telegram delivery don't trigger the telegram-client import.
- **Shared types are local.** Each module defines its own types.py. No shared types package across toolkit modules.
- **Prompt Regression LLM access is injected.** The judge uses an llm_client-shaped object supplied by the consumer, so the module does not import LLM Client directly.
- **Structured LLM access is injected.** Structured completion uses an llm_client-shaped object supplied by the consumer, so the module does not import LLM Client directly.
- **Consumer coupling is one-way.** Application projects import from toolkit. Toolkit never imports from application projects.
- Adding a new module is purely additive — no existing modules or consumers are affected.
- Adding a new provider/strategy to an existing module is internal — consumers are not affected if they use the tier/strategy abstraction.

## Key Decisions

D-1: No cross-dependencies between toolkit modules
Date: 2026-04-04 | Status: Closed
Decision: Each toolkit module is fully independent. Even where a conceptual relationship exists (clustering operates on embeddings), there is no code-level dependency.
Rationale: Independence means any module can be used alone. A project that needs only embeddings doesn't pull in clustering, LLM, or Telegram. This also means no diamond dependency problems.
Revisit if: Two modules develop a genuine shared abstraction that can't be duplicated without drift risk.

D-2: Adapted from TGBot, not forked
Date: 2026-04-04 | Status: Closed
Decision: LLM Client and Telegram Client are adapted from TGBot's working code, not forked as copies. TGBot will eventually switch to importing from toolkit.
Rationale: TGBot's modules are tested and deployed. Adapting (generalizing interfaces, removing TGBot-specific logic) preserves the tested core while making it reusable.
Revisit if: Adaptation requires so many changes that starting fresh would be cleaner.

D-3: Model/strategy as configuration, not code
Date: 2026-04-04 | Status: Closed
Decision: Embedding model, clustering strategy, and LLM provider are configuration parameters. Consumers specify what they want; toolkit modules handle the dispatch.
Rationale: Consumers should not need code changes when switching models or strategies. This is the primary value of the abstraction.
Revisit if: A new model/strategy requires a fundamentally different interface (not just different parameters).

D-4: Feedback Collector decouples from Phosphene's memory model via duck typing
Date: 2026-06-02 | Status: Closed
Decision: When `feedback_collector` was extracted from Phosphene, its prior static import of `NoteInput` / `NotePatch` from `phosphene.memory_store` was replaced with internal `_NoteInput` / `_NotePatch` dataclasses defined in `toolkit.feedback_collector.types`. The internal dataclasses mirror Phosphene's field names and types exactly. The collector requires a `memory_store` instance that structurally supports `get_note(id)`, `store_note(note)`, and `update_note(id, patch)` — Phosphene's `MemoryStore` satisfies this by duck typing, with no Phosphene-side wiring change.
Rationale: Avoids introducing a `toolkit.feedback_collector → phosphene.memory_store` cross-project import, which would violate the consumer-coupling direction (toolkit never imports from consumer projects). Avoids introducing a `toolkit.feedback_collector → toolkit.memory_store` cross-module dep, which would violate D-1. Duck typing keeps the contract honest without locking the consumer to a specific note shape.
Revisit if: The internal `_NoteInput` / `_NotePatch` shapes drift from real consumer memory APIs and need to become a proper exported Protocol with declared methods.

## Provisional Contracts

- **Embedding cache interface** — the caching mechanism (in-memory, disk, or external) is not yet decided. The ARCH file specifies that caching exists and is keyed to model+input; the storage backend is provisional.
- **LLM Client subscription rotation** — TGBot uses a single provider. Phosphene needs multi-provider rotation with budget tracking. The rotation logic is specified in the ARCH file but untested. Resolve during Phosphene implementation.
- **JSON-RPC Client inclusion** — currently only codexbot consumes this pattern. Include in toolkit if a second consumer needs subprocess JSON-RPC, or extract early if the cleaner codexbot architecture justifies the cost.
