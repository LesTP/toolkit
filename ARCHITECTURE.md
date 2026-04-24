# Toolkit — Architecture

## Component Map

| Component | Responsibility | Dependencies | Provenance |
|-----------|---------------|--------------|------------|
| Embedding | Text → vector embeddings. Batch encoding, caching, configurable model. | none (leaf) | New |
| Clustering | Semantic grouping over embeddings. Pluggable strategies (HDBSCAN, RAPTOR-style recursive). | none (leaf) | New |
| LLM Client | Provider-agnostic LLM API. Model tiers, rate-limit tracking, multi-provider rotation. | none (leaf) | Adapted from TGBot summarization/client.py |
| Telegram Client | Telegram Bot API: send messages, receive updates (long polling), edit messages, MarkdownV2 formatting, inline keyboards, message splitting, Telegraph overflow. | none (leaf) | Sending adapted from TGBot delivery/; receiving adapted from codexbot telegram_adapter |
| JSON-RPC Client | Async JSON-RPC 2.0 client over stdio. Request-response correlation, notification routing, subprocess transport. | none (leaf) | Extracted from codexbot codex_client.py |

## Data Flow

### Core Objects
- **EmbeddingResult** — ndarray of vectors + model identifier + input hash (for cache validation)
- **ClusterResult** — cluster assignments (int array), cluster count, noise label count, strategy used
- **LLMResponse** — content (str), model used, token usage (input/output counts), provider name
- **SendResult** — success (bool), message_id (int|None), error (str|None)
- **TelegramUpdate** — chat_id, user_id, message_text, command, args, message_id, raw

### Flow
No data flows between toolkit modules. Each is a leaf consumed independently by application projects. Application projects wire them together:

```
Year-in-Search:  HN titles → Embedding → Clustering → (labels via LLM Client)
Phosphene:       Source content → Embedding → Memory Store ← Clustering ← Distillation (via LLM Client)
                 Generator output → Telegram Client / Discord
TGBot:           Repo content → LLM Client → Telegram Client
Codexbot:        Telegram updates → Telegram Client (polling) → Command Router
                 Model queries → JSON-RPC Client → Codex app-server
```

## Implementation Sequence

| Order | Module | Rationale | Status |
|-------|--------|-----------|--------|
| 1 | Embedding | Leaf, simplest module. Year-in-Search needs it first. | Phase 2 complete |
| 2 | Clustering | Leaf, depends on Embedding outputs conceptually but not as a code dependency. Year-in-Search needs both. | Not started |
| 3 | LLM Client | Leaf, more complex (multi-provider, rate limits). Builds on TGBot's tested AnthropicProvider. | Complete |
| 4 | Telegram Client | Leaf. Sending side working in TGBot, receiving side working in codexbot. Merge rather than new build. | Complete |
| 5 | JSON-RPC Client | Leaf. Working in codexbot. Extract if second consumer materializes. | Complete |

## Coupling Notes

- **No cross-dependencies.** Toolkit modules never import from each other. Embedding does not depend on Clustering. LLM Client does not depend on Telegram Client. Each is independently installable.
- **Shared types are local.** Each module defines its own types.py. No shared types package across toolkit modules.
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

## Provisional Contracts

- **Embedding cache interface** — the caching mechanism (in-memory, disk, or external) is not yet decided. The ARCH file specifies that caching exists and is keyed to model+input; the storage backend is provisional.
- **LLM Client subscription rotation** — TGBot uses a single provider. Phosphene needs multi-provider rotation with budget tracking. The rotation logic is specified in the ARCH file but untested. Resolve during Phosphene implementation.
- **Clustering RAPTOR strategy** — HDBSCAN is well-understood. The RAPTOR-style recursive strategy is specified as an interface but the implementation details (how to do recursive summarization within the clustering module vs. delegating to the consumer) need resolution. Resolve during Phosphene distillation implementation.
- **JSON-RPC Client inclusion** — currently only codexbot consumes this pattern. Include in toolkit if a second consumer needs subprocess JSON-RPC, or extract early if the cleaner codexbot architecture justifies the cost.
