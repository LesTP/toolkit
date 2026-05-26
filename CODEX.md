# Codex Worker Adapter — Toolkit

> **Contract:** Follow `WORKER_SPEC.md` for iteration lifecycle, allowed actions,
> one-action rule, escalation conditions, and output contract. This file covers
> Codex-specific mechanics only.

## Framework
This project follows the e2e governance framework (see `GOVERNANCE.md`, symlinked from `../e2e/`).

## Required Reading — Every Iteration

You do not have `@`-reference loading. You must explicitly read these files at
the start of every iteration before taking any action.

**CRITICAL: Minimize tool calls.** Each tool call round-trips through the full
context window. Combine reads into as few shell commands as possible.

### Tier 1 — Always (mandatory, every iteration)

Read this file, WORKER_SPEC.md, and DEVPLAN.md in a **single command**:

```bash
cat CODEX.md && echo '---SPLIT---' && cat WORKER_SPEC.md && echo '---SPLIT---' && cat DEVPLAN.md
```

**DEVLOG.md:** Append new entries at the bottom (newest last). During phase close, archive the previous phase's entries to `DEVLOG_archive.md`. (Toolkit's existing DEVLOG currently has newest entries at top — realign during the next phase close.)

### Tier 2 — Current module (mandatory for step/review/complete actions)

After determining the active module from DEVPLAN's Current Status, read the
relevant ARCH file. Combine with source files in the **same command**:

```bash
cat ARCH_<module>.md && echo '---SPLIT---' && cat src/toolkit/<module>/types.py && echo '---SPLIT---' && cat src/toolkit/<module>/core.py
```

| Module | ARCH file | Source dir | Tests dir |
|--------|-----------|------------|-----------|
| embedding | `ARCH_embedding.md` | `src/toolkit/embedding/` | `tests/embedding/` |
| clustering | `ARCH_clustering.md` | `src/toolkit/clustering/` | `tests/clustering/` |
| llm_client | `ARCH_llm_client.md` | `src/toolkit/llm_client/` | `tests/llm_client/` |
| telegram_client | `ARCH_telegram_client.md` | `src/toolkit/telegram_client/` | (none yet) |
| json_rpc | `ARCH_json_rpc.md` | `src/toolkit/json_rpc/` | `tests/json_rpc/` |
| cost_accountant | `ARCH_cost_accountant.md` | `src/toolkit/cost_accountant/` (to create) | `tests/cost_accountant/` (to create) |

### Tier 3 — On demand (read only when needed)
- `PROJECT.md` — only during Phase Plan actions
- `ARCHITECTURE.md` — only during Phase Plan or cross-module wiring
- `GOVERNANCE.md` — only if unsure about process

### Read efficiency rules
- **Combine related reads** into one `cat A && echo '---' && cat B` command
- **Never read one file per tool call** when you need multiple files
- **Combine source + test reads:** `cat src/toolkit/<module>/core.py && echo '---' && cat tests/<module>/test_core.py`
- **Fresh reads before edits** — re-read immediately before editing, not at iteration start

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
- **Lazy imports for heavy deps:** `hdbscan`, `umap`, `sentence_transformers` are imported inside functions, not at module top.

## Codex-Specific Tool Rules
- **No `@` references.** Read files explicitly using CLI. When a file contains `@FILENAME` references, treat them as file paths to read.
- **Minimize tool calls.** Every tool call re-processes the full context. Combine multiple file reads, greps, and short commands into single shell invocations.
- **Command files shared with Claude.** Action procedures live in `.claude/commands/*.md`. Read these files and follow their instructions the same way Claude does — the content is backend-agnostic.
- **Fresh reads before edits.** Before editing any file (especially DEVPLAN.md), read it immediately before the edit — not at the start of the iteration.
- **Shell usage.** Use CLI tools directly for builds, tests, git operations, file discovery, and search.
- **Search tool availability.** This loop environment may not have `rg` installed. Before using `rg`, check availability with `command -v rg`. If absent, use portable fallbacks: `find` for file discovery, `grep -RIn` for text search, `sed -n` for bounded file reads.

## Action Instructions

WORKER_SPEC.md defines four allowed actions. Here is how to execute each in
Codex. Perform **exactly one** per iteration unless `steps_remaining` > 0
(see WORKER_SPEC.md §4 for multi-step budget).

### Phase Plan
**When:** No active phase for the current module.
1. Read `.claude/commands/phase-plan.md` and follow its instructions.
2. Commit with message: `phase-plan: <module>.<phase> — <summary>`.
3. Emit exit signal and stop (or continue to first step if steps_remaining > 0).

### Step Execution
**When:** A phase is in progress with remaining steps.
1. Pick the next step from DEVPLAN. Do all file read/write work.
2. Run builds, tests, and git operations as needed.
3. Read `.claude/commands/step-done.md` and follow its instructions.
4. Emit exit signal and stop. Do **not** start the next step unless `steps_remaining > 0`.

### Phase Review
**When:** All steps in the current phase are complete.
1. Read `.claude/commands/phase-review.md` and follow its instructions.
2. Emit exit signal and stop.

### Phase Complete
**When:** Review is done and fixes (if any) are applied.
1. Read `.claude/commands/phase-complete.md` and follow its instructions.
2. Emit exit signal and stop.

## Output Contract

End every iteration with exactly these five lines — no additional text after:

```
EXIT: 0 | 1 | 2
REASON: <one-line summary>
ACTION_TYPE: PLAN | EXECUTE | REVIEW | CLOSE
ACTION_ID: <phase.step>
STEPS_COMPLETED: <number of actions performed in this invocation>
```

## Autonomy

When invoked in autonomous mode, execute the action and emit the exit signal
without waiting for human input. In supervised mode, surface proposed changes
for approval before committing.

See WORKER_SPEC.md §8 for full mode definitions.
