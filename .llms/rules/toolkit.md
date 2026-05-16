# Toolkit

## Framework
This project follows the From Idea to Code governance framework.

## Always Loaded
- @PROJECT.md — scope, constraints, "second consumer" rule
- @ARCHITECTURE.md — component map, coupling notes, key decisions

## Load for Current Module
Determine the active module from ARCHITECTURE.md's Implementation Sequence table — first module without "Complete" status. Then load:
- ARCH_[module].md — module contract and interface spec
- DEVPLAN.md — current status, phase plan, cold start summary
- DEVLOG.md — history (load when debugging or reviewing)

## Available Modules
- Embedding — text → vector embeddings (ARCH_embedding.md)
- Clustering — semantic grouping over embeddings (ARCH_clustering.md)
- LLM Client — provider-agnostic LLM API (ARCH_llm_client.md)
- Telegram Client — Telegram Bot API send/receive/edit (ARCH_telegram_client.md)
- JSON-RPC Client — async JSON-RPC 2.0 over stdio (ARCH_json_rpc.md) [candidate]
- Cost Accountant — cost tracking and budget enforcement for LLM API calls (ARCH_cost_accountant.md)

## Cross-Project References
- VALIDATION_NOTES.md — interface checks against Year-in-Search, Phosphene, Codexbot, and TGBot migration notes

## Known Consumers
- Phosphene: c:\Users\myeluashvili\claude-code-workspace\projects\phosphene\
- Year-in-Search: c:\Users\myeluashvili\claude-code-workspace\projects\year-in-search\
- TGBot: c:\Users\myeluashvili\claude-code-workspace\projects\TGbot\
- Codexbot: p:\shared\codexbot\
