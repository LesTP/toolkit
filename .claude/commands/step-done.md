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
5. Briefly state what the next step is according to the DEVPLAN

**If supervised:** Do not start the next step until I say so.

State transition and exit are handled by WORKER_SPEC §3–§4. Do not
duplicate that logic here.
