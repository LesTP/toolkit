---
name: step-done
description: Step completion — log, commit or amend, prep for next step
---

Current step is complete. Tests have already passed.

Parse $ARGUMENTS for --amend or --commit (default is --commit).

1. Present a summary of changes made in this step
2. Update DEVLOG with a structured entry:
   - Header: `### Step [N]: [short title]`
   - Structured fields: Mode, Outcome, Contract changes
   - Followed by prose: what was done, decisions, issues
3. If this step modified a shared contract, list affected documents in the
   Contract changes field
4. If --commit: create a new commit with a descriptive message
   If --amend: amend the previous commit
5. Update DEVPLAN frontmatter:
   - If this was the last step in the phase: set `state: review`
   - Otherwise: keep `state: execute`
   - If `steps_remaining` is present: decrement it by 1
6. **Turn health check** (Codex only):
   If `ITERATION_JSONL` was provided in the prompt, check total turns:
   ```bash
   grep -c '"item.completed"' "$ITERATION_JSONL"
   ```
   Compare to `steps_completed × 50`. If exceeded: ESCALATE — the worker
   is spiraling. This is a safety check, not the budget mechanism.
7. Briefly state what the next step is according to the DEVPLAN

**If autonomous:**
Commit. If `steps_remaining > 0` and state is `plan` or `execute`
and turn health check passed: continue to next action.
Otherwise: emit exit signal.

**If supervised:** Do not start the next step until I say so.
