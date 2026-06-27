# Claude Worker Adapter — Toolkit

> **Contract:** Backend-specific mechanics for Claude workers. The universal
> loop contract (identity, main loop, escalation, output contract,
> prohibitions) lives in `WORKER_SPEC.md` and arrives in your prompt
> pre-assembled — you do not read it. Action procedures live in
> `instructions/$ACTION.md` and also arrive pre-assembled. This adapter
> covers what is **Claude-specific** plus what is **project-specific**.

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
  are imported inside functions, not at module top, to keep import cost off
  consumers that don't use those paths.
- **Provenance:** several modules were adapted from TGBot / codexbot / Diplomat
  / Phosphene. Retain tested patterns; do not rewrite for style.

## Claude-Specific Tool Rules

- **Edit tool requires fresh reads.** Before editing any source or test file,
  read it immediately before the edit — not at the start of the iteration.
  Governance state arrived fresh in your prompt; this rule applies to source
  files only.
- **No subagent spawning for routine work.** Do NOT spawn `Agent(Explore)`
  subagents for simple file discovery — use `bash find` or `bash ls`
  instead. Subagents are appropriate for genuinely open-ended research.
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

## Runner Info

**Runner:** `i2c run` invokes `claude -p` per iteration with the assembled
prompt on stdin and logs to `logs/loop/`. Supervised slash-command wrappers
(for interactive use) ship with i2c; you do not read them in autonomous mode —
the same procedures arrive in your assembled prompt via `instructions/*.md`.

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
