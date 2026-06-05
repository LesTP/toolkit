# Toolkit

## Spark
> Cross-project modules keep getting rebuilt from scratch. A shared building-block library with typed interfaces lets agent and pipeline projects reuse tested infrastructure instead of reinventing it.

## What This Is
A personal building-block library of Python modules shared across multiple projects. Each module is independently installable and has typed dataclass interfaces. Leaf modules have no toolkit dependencies; a small number of composing modules wrap exactly one leaf module (enumerated in Scope). Modules enter the toolkit when a second project needs them — not speculatively.

## Audience
The author's own projects. Currently: Phosphene (autonomous personality agent), Year-in-Search (HN topic visualization pipeline), TGBot (GitHub digest bot), Codexbot (Telegram-based Codex orchestrator control surface), Diplomat (LLM-mediated negotiation experiments).

## Scope

### Core (leaf — no toolkit deps)
- Embedding: text → vector embeddings with caching and configurable model
- Clustering: semantic grouping over embeddings with pluggable strategies (HDBSCAN, RAPTOR-style recursive)
- LLM Client: provider-agnostic API abstraction (Anthropic, OpenAI, Gemini, OpenRouter) with model tiers and lazy SDK loading
- Telegram Client: Bot API messaging and receiving — send messages, long-poll for updates, edit messages, MarkdownV2 formatting, inline keyboards, message splitting
- JSON-RPC Client: async JSON-RPC 2.0 over stdio or WebSocket — request-response correlation, notification routing, subprocess transport
- Source Ingestion: adapter framework for external content (RSS, Telegram channel, Reddit, human-share DM, corpus importers for LiveJournal/Blogspot/text/Facebook/Twitter) with durable last-seen markers
- Feedback Collector: normalizes platform feedback signals (reactions, replies, forwards, silence) into structured events written to a duck-typed memory store
- Prompt Regression: scenario-based prompt regression framework — JSON path checks and LLM-as-judge evaluation
- Structured LLM: LLM JSON extraction with schema injection, validation, and retry
- Coaching: tag-based operator-input parser — YAML-driven tag routes and slash-command vocabulary, parses to typed `CoachingEvent` / `Command`

### Core (composing — depends on one leaf module)
- Cost Accountant → LLM Client: cost tracking and budget enforcement — wraps LLM Client with pre-call estimation, per-call/operation/session budget checking, append-only JSONL ledger, rate-limit and spending-cap abort
- Gateway → Telegram Client (optional, runtime import): multi-platform message bus with Telegram/log/fake adapters, inbound + outbound messaging, feedback signal dispatch

### Flexible
- [deferred] Discord client (when a second project needs it)
- [deferred] Storage abstraction (if TGBot's pattern proves reusable as-is)
- [deferred] Telegraph client (TGBot has one; move if second project needs it)

### Exclusions
- No application logic — toolkit modules are infrastructure, not features
- Leaf modules have zero toolkit dependencies. Composing modules may depend on exactly one leaf module they explicitly wrap or adapt; each such dependency must be enumerated above and justified in the module's ARCH file
- No framework or orchestration layer — consuming projects provide their own wiring
- No speculative modules — second consumer required for inclusion

## Constraints
- **Language:** Python 3.9+
- **Interfaces:** Typed dataclasses at every boundary
- **Independence:** Each module is a standalone package with its own `types.py` and tests. Leaf modules have no imports from other toolkit modules. Composing modules (see Scope) may import exactly one leaf module, declared explicitly in the module's ARCH file.
- **Provenance:** Modules adapted from existing projects (TGBot, codexbot) retain their tested patterns; new modules follow the same conventions

## Prior Art
- **TGBot delivery module** — telegram_client.py, telegraph_client.py, formatting.py. Working, tested, deployed.
- **TGBot summarization module** — client.py with LLMProvider ABC and AnthropicProvider. Working but single-provider.

## Success Criteria
- A consuming project can integrate a toolkit module using only its ARCH file
- Toolkit modules have no knowledge of consuming projects' domain logic
- Adding a new provider/strategy/model to a toolkit module requires no changes in consuming projects

## Risks and Open Questions
- [implementation] **LLM client scope** — TGBot's LLMProvider is Anthropic-only with a simple factory. Phosphene needs multi-provider rotation with rate-limit tracking. The interface must support both the simple case and the complex case without forcing complexity on simple consumers.
- [implementation] **Embedding model flexibility** — Year-in-Search uses all-MiniLM-L6-v2; Phosphene may need larger models. The module must be model-agnostic with caching keyed to model+input.
- [watch] **Module migration friction** — extracting from TGBot means TGBot needs to switch from internal imports to toolkit imports. Track whether this creates deployment issues.

## Extension Points
- Additional clustering strategies beyond HDBSCAN and RAPTOR
- Additional LLM providers beyond Anthropic (OpenAI, Google, OpenRouter)
- Additional platform clients (Discord, Slack) as projects need them

## Size Estimate
Multi-module. Twelve modules (ten leaf + two composing), each a standalone package under `src/toolkit/<module>/`.

---

## Change History
| Date | What Changed | Why |
|------|-------------|-----|
| 2026-04-04 | Initial PROJECT.md | Motivated by Phosphene + Year-in-Search overlap |
| 2026-06-04 | Synced module list to 11 (added gateway, source_ingestion, feedback_collector, prompt_regression, structured_llm); promoted JSON-RPC from Candidate to Core (second consumer materialized via codexbot); documented second cross-dep exception (gateway → telegram_client); generalized cross-dep rule to leaf vs. composing modules; added Diplomat as consumer | Doc drift — PROJECT.md was lagging behind API.md and on-disk state |
| 2026-06-05 | Added Coaching module (12th, leaf). Extracted from Diplomat; Clanker Courts queued as second consumer. | Second-consumer rule satisfied via Diplomat (current) + Clanker Courts (incoming). |
