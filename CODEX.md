# Codex Worker Adapter — Toolkit

> **Contract:** Backend-specific mechanics for Codex workers. The universal
> loop contract (identity, main loop, escalation, output contract,
> prohibitions) lives in `WORKER_SPEC.md` and arrives in your prompt
> pre-assembled — you do not read it. Action procedures live in
> `instructions/$ACTION.md` and also arrive pre-assembled. This adapter
> covers what is **Codex-specific** plus what is **project-specific**.

## Framework

i2c. State lives in `.state/*.json`; you never read or write governance files
directly — everything you need arrives pre-assembled in your prompt, and you
write outcomes back through `i2c state`.

## Available Modules

Toolkit is a library of independent modules consumed by application projects
(Year-in-Search, Phosphene, TGBot, Codexbot, Diplomat, Clanker Courts). All
modules are complete.

**Leaf modules** (no toolkit dependencies):
- `embedding` — text → vector embeddings with caching
- `clustering` — semantic grouping over embeddings; HDBSCAN + RAPTOR strategies
- `llm_client` — provider-agnostic LLM API; model tiers, rate limits, rotation
- `telegram_client` — Telegram Bot API send/receive/edit, MarkdownV2, splitting
- `json_rpc` — async JSON-RPC 2.0 over stdio
- `prompt_regression` — scenario-based prompt regression with LLM-as-judge
  (injected LLM client protocol)
- `structured_llm` — LLM JSON extraction + schema validation (injected client)
- `source_ingestion` — RSS / Telegram channel / Reddit / human-share / corpus
  importers → uniform `ContentItem`
- `feedback_collector` — normalizes platform feedback signals to a duck-typed
  memory store
- `coaching` — tag-based operator-input parser; YAML routes + slash-command
  vocabulary
- `clankmates_client` — subprocess wrapper around the `clankm` CLI + message
  decoders, thread-cursor store, peer-DM screener

**Composing modules** (one approved cross-module dependency each):
- `cost_accountant` → `llm_client` — budget enforcement, JSONL ledger, reporting
- `gateway` → `telegram_client` (optional, runtime import) — multi-platform
  message bus
- `edit_classifier` → `structured_llm` — LLM-as-judge edit-log categorizer

## Project-Specific Notes

- **Language:** Python 3.9+
- **Packaging:** single `pyproject.toml`; modules live under
  `src/toolkit/<module>/`.
- **Module independence:** no imports between toolkit modules except the three
  documented exceptions above (`cost_accountant → llm_client`, `gateway →
  telegram_client` optional, `edit_classifier → structured_llm`). Do not
  introduce a new cross-module import without ESCALATE.
- **Typed boundaries:** each module exposes typed dataclasses in `types.py`;
  public API via `__init__.py`.
- **Tests:** `pytest`, run from the project root: `pytest tests/<module>/`.
  (Environment-specific test gotchas — venv path, `PYTHONPATH`, missing
  `jsonschema` — arrive pre-assembled in `project.json.gotchas`; don't
  duplicate them here.)
- **Lazy imports for heavy deps:** `hdbscan`, `umap`, `sentence_transformers`
  are imported inside functions, not at module top.
- **Provenance:** several modules were adapted from TGBot / codexbot / Diplomat
  / Phosphene. Retain tested patterns; do not rewrite for style.

## Codex-Specific Tool Rules

- **No `@`-reference loading.** Read files explicitly using shell commands.
  When prose contains `@FILENAME` markers, treat them as file paths to read
  with `cat` or `sed -n`.
- **Minimize tool calls.** Every tool call re-processes the full context.
  Combine multiple file reads, greps, and short commands into single shell
  invocations.
  - Bad: `cat A.py` then `cat B.py` (two tool calls).
  - Good: `cat A.py && echo '---' && cat B.py` (one tool call).
  - Bad: `grep foo A` then `grep foo B`.
  - Good: `grep -n foo A B`.
- **Search-tool fallback.** This loop environment may not have `rg`
  installed. Before using `rg`, check availability with `command -v rg`. If
  it is absent, fall back to portable equivalents: `find` for file
  discovery, `grep -RIn` for text search, `sed -n` for bounded file reads.
  Do not repeatedly retry `rg` after it has failed in the same iteration.
- **Fresh reads before edits.** Before editing any source or test file,
  re-read it immediately — not at the start of the iteration. Governance
  arrived fresh in your prompt; this rule applies to source files only.
- **Non-interactive shell only.** The loop has no stdin. Commands that
  open editors (`vim`, `nano`, `git commit` without `-m`,
  `git rebase -i`), prompt for input (`read`, `sudo` without `-n`,
  `ssh` without `-o BatchMode=yes`), or pipe through pagers (`less`,
  `more`, `git log` without `--no-pager`) will hang. To stage part of
  a file, split into discrete edits or use `git restore` to revert
  unwanted parts before `git add`. `git add -p` is interactive-only.
- **State writes go through `i2c state`.** Never use `sed`, `echo >`, or
  direct file edits on `.state/` files. The CLI guarantees atomic,
  schema-validated writes.
- **Use `i2c state --from-file` for multi-line or `$`-laden payloads.**
  Write the JSON to a temp file and pass `--from-file <path>`; bypasses
  shell quoting entirely. Inline-quoting works for short one-line JSON
  without `$` or newlines.

## Turn Health Check (Codex-specific safety)

This is a **safety circuit breaker**, separate from the step budget. The
runner provides `ITERATION_JSONL` in the prompt's environment when
applicable. After each completed action, check the turn count:

```bash
grep -c '"item.completed"' "$ITERATION_JSONL"
```

If `total_turns > actions_performed * 50`, emit the exit signal with `EXIT 2`
and reason `"turn health check exceeded"`. Do **not** continue.

(`actions_performed` here is the worker's internal count of actions taken in
this invocation — typically 1 for EXECUTE/REVIEW/CLOSE — not a field in the
emitted signal.)

Calibration notes (apply judgment, not just the formula):

- The 50-turns-per-step ceiling is calibrated for single-repo work where
  the worker mostly reads, edits, and tests within one project directory.
- **Cross-repo work** (e.g., a step that edits both this project and a
  consumer repo) legitimately needs more tool calls. If you trip the ceiling
  during a clearly-cross-repo step, log the exit and note the cause in the
  devlog `summary` so the orchestrator can decide whether to relax the
  threshold for future cross-repo phases.
- The check is a circuit breaker, not the budgeting mechanism. The step
  budget (`steps_remaining` in `project.json`) is what counts work; this
  is just the safety net against runaway tool churn.

## Runner Info

**Runner:** `i2c run --backend codex` invokes `codex exec` per iteration with
the assembled prompt on stdin and logs to `logs/loop/`. The runner ships an
iteration-specific JSONL log path in the prompt when relevant; that path is the
input to the turn-health check above.

## Output Contract

End every invocation with exactly these two lines — no additional text after:

```
EXIT: 0 | 2
REASON: <one-line summary>
```

| Code | Meaning |
|------|---------|
| 0 | Normal completion — runner reads `.state/project.json` to decide next dispatch |
| 2 | Error — judgment-based escalation or health check tripped |

The runner's parser uses line-anchored regexes. The block can be plain or inside a fenced code block; both work. **Do not omit it** — prose-only output causes the runner to report `exit=2 "signal missing or malformed"` even when the work landed correctly in `.state/` and the commit. Everything else the runner needs (action, phase, step, status) it reads from `.state/project.json` and from what it dispatched.

## Mode

Mode (autonomous vs. supervised) is set by the runner via the assembler's
`--mode` flag. The assembled prompt's framing reflects the active mode:

- **Autonomous** (default): apply fixes, commit, transition state, emit the
  exit signal without waiting for input.
- **Supervised** (`--mode supervised`): the assembled instructions include
  pause-for-approval framing; surface proposed changes before committing.

You do not choose the mode. If the framing in your prompt is ambiguous,
default to autonomous behavior and note the ambiguity in the devlog
`summary`.
