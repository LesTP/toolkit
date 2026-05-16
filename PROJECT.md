# Toolkit

## Spark
> Cross-project modules keep getting rebuilt from scratch. A shared building-block library with typed interfaces lets agent and pipeline projects reuse tested infrastructure instead of reinventing it.

## What This Is
A personal building-block library of Python modules shared across multiple projects. Each module is independently installable, has typed dataclass interfaces, and no cross-dependencies on other toolkit modules. Modules enter the toolkit when a second project needs them — not speculatively.

## Audience
The author's own projects. Currently: Phosphene (autonomous personality agent), Year-in-Search (HN topic visualization pipeline), TGBot (GitHub digest bot), Codexbot (Telegram-based Codex orchestrator control surface).

## Scope

### Core
- Embedding: text → vector embeddings with caching and configurable model
- Clustering: semantic grouping over embeddings with pluggable strategies (HDBSCAN, RAPTOR-style recursive)
- LLM Client: provider-agnostic API abstraction with model tiers, rate-limit tracking, and subscription rotation
- Telegram Client: Bot API messaging and receiving — send messages, long-poll for updates, edit messages, MarkdownV2 formatting, inline keyboards, message splitting, Telegraph overflow
- Cost Accountant: cost tracking and budget enforcement for LLM API calls — wraps LLM Client with pre-call estimation, per-call/operation/session budget checking, append-only JSONL ledger, rate-limit and spending-cap abort, session reporting

### Candidate
- JSON-RPC Client: async JSON-RPC 2.0 over stdio — request-response correlation, notification routing, subprocess transport (include when second consumer materializes)

### Flexible
- [deferred] Discord client (when Phosphene gateway implementation starts)
- [deferred] Storage abstraction (if TGBot's pattern proves reusable as-is)
- [deferred] Telegraph client (TGBot has one; move if second project needs it)

### Exclusions
- No application logic — toolkit modules are infrastructure, not features
- No cross-dependencies between toolkit modules (except Cost Accountant → LLM Client, which is the only approved exception)
- No framework or orchestration layer — consuming projects provide their own wiring
- No speculative modules — second consumer required for inclusion

## Constraints
- **Language:** Python 3.9+
- **Interfaces:** Typed dataclasses at every boundary
- **Independence:** Each module is a standalone package with its own `types.py`, tests, and no imports from other toolkit modules
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
Multi-module. Six independent modules (five leaf + one wrapper), each a standalone package.

---

## Change History
| Date | What Changed | Why |
|------|-------------|-----|
| 2026-04-04 | Initial PROJECT.md | Motivated by Phosphene + Year-in-Search overlap |
