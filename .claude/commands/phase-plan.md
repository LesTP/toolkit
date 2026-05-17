---
name: phase-plan
description: Plan a new phase — Discuss mode sequence
---

We are entering Discuss mode to plan the next phase. Work through this
sequence:

1. Identify the next phase from the DEVPLAN or implementation sequence
2. Determine scope and specific outcomes for this phase
3. Identify the work regime:
   - Build — break into smallest testable steps, create test specs
   - Refine — define goals and constraints, identify first item to show,
     plan a time budget not a step count
   - Explore — define the decision to be made and set a time box

If this is the first phase of a module, update the module's Status in
ARCHITECTURE.md's Implementation Sequence table to "In progress".

Update DEVPLAN with the phase plan. Set frontmatter `state: execute`.
If `steps_remaining` is present, decrement it by 1.
Log scope decisions to DECISIONS.md. Commit.

**If autonomous:**
If `steps_remaining > 0` and state is `execute`: continue to first step.
Otherwise: emit exit signal.

**If supervised:** Present the plan for human review before committing.

Do not write code. This is Discuss mode only.
