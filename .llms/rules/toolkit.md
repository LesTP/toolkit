# Toolkit

## Framework
This project follows the From Idea to Code governance framework.

## Always Loaded
- @PROJECT.md — scope, constraints, "second consumer" rule
- @ARCHITECTURE.md — component map, coupling notes, key decisions
- @API.md — canonical public API signatures for every toolkit module; used directly when building consumer-side fakes

## Load for Current Module
Determine the active module from ARCHITECTURE.md's Implementation Sequence table — first module without "Complete" status. Then load:
- ARCH_[module].md — module contract and interface spec
- DEVPLAN.md — current status, phase plan, cold start summary
- DEVLOG.md — history (load when debugging or reviewing)

## Available Modules

Leaf modules (no toolkit dependencies):
- Embedding — text → vector embeddings (ARCH_embedding.md)
- Clustering — semantic grouping over embeddings (ARCH_clustering.md)
- LLM Client — provider-agnostic LLM API (ARCH_llm_client.md)
- Telegram Client — Telegram Bot API send/receive/edit (ARCH_telegram_client.md)
- JSON-RPC Client — async JSON-RPC 2.0 over stdio or WebSocket (ARCH_json_rpc.md)
- Source Ingestion — RSS / Telegram channel / Reddit / corpus importers (ARCH_source_ingestion.md)
- Feedback Collector — normalizes platform feedback signals to a duck-typed memory store (ARCH_feedback_collector.md)
- Structured LLM — LLM JSON extraction with schema validation and retry (ARCH_structured_llm.md)
- Prompt Regression — scenario-based prompt regression framework with LLM-as-judge (ARCH_prompt_regression.md)
- Coaching — tag-based operator-input parser, YAML-driven routes + slash-command vocabulary (ARCH_coaching.md)
- Edit Classifier — LLM-as-judge categorical classifier for review-gate edit logs (ARCH_edit_classifier.md)

Composing modules (depend on exactly one leaf module):
- Cost Accountant → LLM Client — cost tracking and budget enforcement (ARCH_cost_accountant.md)
- Gateway → Telegram Client (optional, runtime import) — multi-platform message bus (ARCH_gateway.md)

## Cross-Project References
- VALIDATION_NOTES.md — interface checks against Year-in-Search, Phosphene, Codexbot, Diplomat, and TGBot migration notes

## Consumer contract (shared library — do not fork)
Toolkit is the fleet's **shared library**: consumers (phosphene, masorah, diplomat,
codexbot, …) **import/consume its modules as-is and never modify or fork them**.
Fixes and new capability land *here*, behind the module's public API (`API.md`),
so every consumer benefits and no divergent copies accrue. If a consumer needs a
change, change it in toolkit (respecting the "second consumer" rule in PROJECT.md),
not in the consumer.

## Known Consumers
- Phosphene: c:\Users\myeluashvili\claude-code-workspace\projects\phosphene\
- Year-in-Search: c:\Users\myeluashvili\claude-code-workspace\projects\year-in-search\
- TGBot: c:\Users\myeluashvili\claude-code-workspace\projects\TGbot\
- Codexbot: p:\shared\codexbot\
- Diplomat: p:\shared\diplomat\
