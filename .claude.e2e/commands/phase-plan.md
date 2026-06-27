---
name: phase-plan
description: Plan a new phase — Discuss mode sequence
---

We are entering Discuss mode to plan the next phase.

1. Identify the next phase from the DEVPLAN or implementation sequence
2. Determine scope and specific outcomes for this phase
3. Identify the work regime:
   - Build — break into smallest testable steps, create test specs
   - Refine — define goals and constraints, identify first item to show,
     plan a time budget not a step count
   - Explore — define the decision to be made and set a time box
4. If this is the first phase of a module, update the module's Status in
   ARCHITECTURE.md's Implementation Sequence table to "In progress"
5. Update DEVPLAN with the phase plan
6. Log scope decisions to DECISIONS.md
7. Commit

**If supervised:** Present the plan for human review before committing.

Do not write code. This is Discuss mode only.

State transition and exit are handled by WORKER_SPEC §3–§4. Do not
duplicate that logic here.
