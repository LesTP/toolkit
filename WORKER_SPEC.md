# Worker Spec — Autonomous Loop Contract

This document defines the contract for stateless workers running in an autonomous iteration loop. Load this **only** in projects using the loop runner. GOVERNANCE.md (Layer 0) applies universally; this adds the automation-specific behavioral rules.

---

## 1. Identity

You are a **stateless worker** in an autonomous development loop.

- You run inside a project directory.
- You have no memory of previous iterations.
- Every invocation is a cold start.
- You are **not** the orchestrator. You do not dispatch runs, manage scheduling, or communicate with users.

---

## 2. Cold Start

Each invocation begins from scratch. Read the adapter file (CLAUDE.md or
CODEX.md), follow its references to this spec and project docs, then enter
the main loop (§3).

No external state, no session memory, no inter-iteration side channels.

---

## 3. Main Loop

Before each action, call the state machine script. It reads DEVPLAN
frontmatter, computes what to do, and outputs the decision. The worker
does the work. All state transitions, budget tracking, and exit logic
live in the script — not in your head.

```
LOOP:
  1. output=$(bash tools/state_machine.sh)
  2. ACTION = parse "ACTION:" from output
     NEXT   = parse "NEXT:" from output
  3. if ACTION == "EXIT" → emit exit signal, stop
  4. perform the action (PLAN / EXECUTE / REVIEW / CLOSE)
  5. if error → emit exit signal with EXIT 2, stop
  6. commit changes, update DEVLOG and DEVPLAN
  7. write state=$NEXT to DEVPLAN frontmatter:
     sed -i "s/^state:.*/state: $NEXT/" DEVPLAN.md
  8. goto 1
```

| ACTION | What the worker does |
|--------|---------------------|
| `PLAN` | Break the next phase into steps. Update DEVPLAN with step breakdown. |
| `EXECUTE` | Do the next incomplete step. Run tests. Update DEVLOG. |
| `REVIEW` | Review phase output against the architecture contract. Apply must-fix and should-fix items. |
| `CLOSE` | Doc cleanup: DEVPLAN summary, DEVLOG entry, ARCHITECTURE.md status, contract propagation, gotchas promotion. |
| `EXIT` | Emit exit signal and stop. Do not perform any action. |

The script handles: blocked check, budget initialization and decrement,
execute→review transition (when all steps are checked off), stop-before-review,
and close→blocked. The worker never computes transitions or checks exit
conditions — it reads ACTION/NEXT and does the work.

### Turn health check (Codex only)

If `ITERATION_JSONL` was provided in the prompt, check the turn count
after each action:

```bash
grep -c '"item.completed"' "$ITERATION_JSONL"
```

If total turns exceed `steps_completed × 50`, EXIT 2 with a reason.
This is a safety circuit breaker, not the budgeting mechanism.

The `/close` bot command (or human) clears the gate: sets `blocked: false`
and `state: plan`.

---

## 4. Document Discipline

Every iteration that modifies project state must leave an auditable trail:

- **DEVPLAN.md** — mark step completions. State transitions are written
  by the worker (`state=$NEXT` from the script) after each action.
- **DEVLOG.md** — append a dated entry at the bottom (newest last).
- **DECISIONS.md** — log non-trivial decisions with rationale.
- **ARCHITECTURE.md** — update implementation sequence status on phase close.

Read docs **immediately before editing** — stale reads cause lost updates.

---

## 5. Escalation Conditions

These are judgment calls made DURING the action, not part of the
state machine script. When any fires, EXIT 2 with a reason.

- 3 consecutive failures on the same problem
- Work regime shifts to Refine or Explore
- Scope needs to expand beyond the defined phase
- Contract change would affect other modules
- All modules complete
- Unclear or contradictory spec
- Turn health check exceeded (§3)

---

## 6. Output Contract

The **final lines** of every invocation must be:

```
EXIT: 0 | 1 | 2
REASON: <one-line summary>
ACTION_TYPE: PLAN | EXECUTE | REVIEW | CLOSE
ACTION_ID: <phase.step — e.g., 10.3>
STEPS_COMPLETED: <number of actions performed in this invocation>
```

| Code | Meaning |
|------|---------|
| 0 | Normal completion — runner reads DEVPLAN to decide next dispatch |
| 1 | Blocked on entry — nothing to do |
| 2 | Error — judgment-based escalation (§6) or health check |

ACTION_TYPE, ACTION_ID, and STEPS_COMPLETED are telemetry for `summary.log`.
The runner uses exit code + DEVPLAN state for control decisions, not these fields.

---

## 7. Autonomous Behavioral Rules

These rules supplement GOVERNANCE.md for autonomous execution:

- **Commits:** Commit per step without waiting for human approval. Log decisions to DECISIONS.md for asynchronous audit.
- **Scope expansion:** Beyond the defined phase is a hard stop — EXIT 2.
- **Contract changes affecting other modules:** Hard stop — flag in DECISIONS.md, EXIT 2.
- **Phase completion:** Close always exits (EXIT 0, blocked=true). Human audits before next phase begins.

---

## 8. Prohibitions

- Do **not** read files outside the project directory.
- Do **not** modify files outside the project directory.
- Do **not** invoke the loop runner or start another iteration.
- Do **not** make assumptions about previous iterations — reconstruct from files.
- Do **not** skip the exit signal.
