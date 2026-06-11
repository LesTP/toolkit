---
name: phase-review
description: End-of-phase code review before completion
---

Review all code from the current phase.

Priority #1: Preserve existing functionality
Priority #2: Simplify and reduce code

Check for:
- Dead code or unused imports
- Architecture drift from the spec
- Opportunities to simplify

Present findings organized as:
- Must fix (correctness, architecture violations)
- Should fix (simplification, cleanup)
- Optional (style, minor improvements)

**If autonomous:** Apply must-fix and should-fix items. Log skip decisions
for optional items to DECISIONS.md. Commit.
**If supervised:** Do not implement. Wait for direction on what to fix.

State transition and exit are handled by WORKER_SPEC §3. Do not duplicate
that logic here — always return to the main loop (step 1: call state_machine.sh)
after completing this action.
