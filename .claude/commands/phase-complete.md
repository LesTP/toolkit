---
name: phase-complete
description: Phase completion checklist — run after review issues are resolved
---

Execute the phase completion protocol:

1. Run phase-level tests and confirm they pass
2. If any fakes cover real external dependencies, confirm a dependency
   probe has passed for each (see `/dependency-probe`)
3. Read each governance doc and identify needed updates:
   - **DEVPLAN.md**: Update Current Status. Reduce completed phase to a
     one-line summary with DEVLOG reference
   - **DEVPLAN.md frontmatter**: `blocked: true` is set by WORKER_SPEC §4
     exit check rule 1 (close is terminal). Do not set it manually here.
   - **DEVLOG.md**: Add phase completion entry at the bottom. Archive the
     previous phase's entries to `DEVLOG_archive.md`
   - **ARCHITECTURE.md**: Update Implementation Sequence table status.
     Format: "Phase N complete" after each phase, or "Complete" if this
     was the module's final phase
   - **DECISIONS.md**: Close any Open decisions resolved by this phase
   - **PROJECT.md**: Close any Open risks resolved by this phase
4. DEVLOG learning review — scan this phase's entries for trial-and-error
   patterns. Extract prescriptive one-liners and promote to DEVPLAN Gotchas
5. Contract Changes scan — scan DEVLOG for Contract Changes markers. List
   affected upstream documents and flag what needs propagation
6. Integration check — if this phase modified cross-module types or wired
   modules together, run `/integration-check` between affected module pairs
7. Make all updates identified above. Commit
8. Present summary of everything done

**If supervised:** Do not commit. Wait for explicit confirmation.

State transition and exit are handled by WORKER_SPEC §3. Do not duplicate
that logic here — always return to the main loop (step 1: call state_machine.sh)
after completing this action.
