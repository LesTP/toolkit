# Claude Worker Adapter — Toolkit

> **Contract:** Follow `WORKER_SPEC.md` for iteration lifecycle, allowed actions,
> one-action rule, escalation conditions, and output contract. This file covers
> Claude-specific mechanics only.

## Framework
This project follows the e2e governance framework (see `GOVERNANCE.md`, symlinked from `../e2e/`).

## Required Reading — Every Iteration

Context loading is tiered to control cache size. Each turn re-reads the cached
prefix; smaller prefix → fewer cache-read tokens × turn count. Keep tiering
consistent with `CODEX.md`.

### Tier 1 — Always (mandatory, every iteration)

Auto-loaded via @-references:

- @DEVPLAN.md — current status, cold start summary, gotchas
- @WORKER_SPEC.md — backend-agnostic worker contract

### Tier 2 — Current module (mandatory for STEP / REVIEW / COMPLETE)

After determining the active module from DEVPLAN's Current Status, read the
relevant ARCH file using the lookup table below. Combine with source files
you intend to inspect or edit in the same turn when possible.

| Module | ARCH file | Source dir | Tests dir |
|--------|-----------|------------|-----------|
| embedding | `ARCH_embedding.md` | `src/toolkit/embedding/` | `tests/embedding/` |
| clustering | `ARCH_clustering.md` | `src/toolkit/clustering/` | `tests/clustering/` |
| llm_client | `ARCH_llm_client.md` | `src/toolkit/llm_client/` | `tests/llm_client/` |
| telegram_client | `ARCH_telegram_client.md` | `src/toolkit/telegram_client/` | (none yet) |
| json_rpc | `ARCH_json_rpc.md` | `src/toolkit/json_rpc/` | `tests/json_rpc/` |
| cost_accountant | `ARCH_cost_accountant.md` | `src/toolkit/cost_accountant/` (to create) | `tests/cost_accountant/` (to create) |

### Tier 3 — On demand (read only when needed)

Do NOT load these unconditionally. Read only when the action requires them:

- `PROJECT.md` — only during Phase Plan (scope, constraints, success criteria)
- `ARCHITECTURE.md` — only during Phase Plan, or when reasoning about cross-module wiring
- `GOVERNANCE.md` — only if uncertain about process (regimes, modes, escalation rules)

### Tier 4 — Reference only (load explicitly when relevant)

- `DECISIONS.md` — read during Phase Review to verify no contract drift since prior decisions; otherwise on demand
- `DEVLOG.md` — read during Phase Complete (DEVLOG learning review per GOVERNANCE.md)

**DEVLOG.md:** Append new entries at the bottom (newest last). During phase close, archive the previous phase's entries to `DEVLOG_archive.md`. (Toolkit's existing DEVLOG currently has newest entries at top — realign during the next phase close.)

## Available Modules

**Track — Standalone modules** (no inter-toolkit dependencies):
- **embedding** — text → vector embeddings with caching (complete, 43 tests)
- **clustering** — semantic grouping over embeddings; HDBSCAN + RAPTOR strategies (complete, 48 tests)
- **llm_client** — provider-agnostic LLM API abstraction with model tiers and rate limits (complete)
- **telegram_client** — Telegram Bot API messaging (complete)
- **json_rpc** — async JSON-RPC 2.0 over stdio (complete)

**Track — Wrapper modules** (one approved cross-toolkit dependency):
- **cost_accountant** — wraps `llm_client` with pre-call budget enforcement, JSONL ledger, session reporting (active — Phase 1 not started, ARCH spec written)

## Project-Specific Notes

- **Language:** Python 3.9+
- **Packaging:** Single `pyproject.toml`; modules live under `src/toolkit/<module>/`
- **Module independence:** No imports between toolkit modules. The single exception is `cost_accountant → llm_client`. Do not introduce new cross-module imports without ESCALATE.
- **Typed boundaries:** Each module exposes typed dataclasses in `types.py`. Public API via `__init__.py`.
- **Tests:** `pytest`. Run from project root: `pytest tests/<module>/`.
- **Lazy imports for heavy deps:** `hdbscan`, `umap`, `sentence_transformers` are imported inside functions, not at module top — keeps import cost off consumers that don't use those code paths.
- **Provenance:** Some modules were adapted from `TGBot` / `codexbot`. Retain tested patterns; do not rewrite for style.

## Claude-Specific Tool Rules
- **Edit tool requires fresh reads:** Before editing any file (especially DEVPLAN.md), read it immediately before the edit — not at the start of the iteration.
- **No subagent spawning for simple tasks:** Do NOT spawn Agent(Explore) subagents for simple file discovery — use `bash find` or `bash ls` instead.

## Claude-Specific Runner Info
**Runner:** `run-iteration.sh` — runs `claude -p` per iteration, logs to `logs/loop/`.

**Slash commands:** Project commands in `.claude/commands/` (symlinked from `../e2e/COMMANDS/`) — these are NOT Skill-tool skills. To use them, read the `.md` file and follow its instructions. Do NOT call them via the Skill tool.

| Action (from WORKER_SPEC) | Claude command file |
|---------------------------|---------------------|
| Phase Plan | `.claude/commands/phase-plan.md` |
| Step Execution | `.claude/commands/step-done.md` |
| Phase Review | `.claude/commands/phase-review.md` |
| Phase Complete | `.claude/commands/phase-complete.md` |

## Autonomy
This project supports autonomous execution. When invoked with
`autonomous: true` in the prompt, commands auto-proceed and the agent follows
`WORKER_SPEC.md`. Otherwise, commands pause for human approval.

See WORKER_SPEC.md §8 for mode definitions (autonomous vs. supervised).
