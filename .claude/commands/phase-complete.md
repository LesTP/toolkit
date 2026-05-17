---
name: phase-complete
description: Phase completion checklist — run after review issues are resolved
---

Execute the phase completion protocol:

1. Run phase-level tests and confirm they pass.
2. Read each governance doc and identify needed updates:
   - **DEVPLAN.md**: Update Current Status. Reduce completed phase to a one-line
     summary with DEVLOG reference. Promote any new Gotchas (from steps 3–4 below).
   - **DEVPLAN.md frontmatter**: Set `blocked: true`.
     The `/close` bot command clears the gate by setting `blocked: false`
     and `state: plan`. Do not write "awaiting human audit" in prose —
     the frontmatter `blocked` field is the single source of truth for gating.
   - **DEVLOG.md**: Add phase completion entry at the bottom. Archive the
     previous phase's DEVLOG entries to `DEVLOG_archive.md` (append at top
     of archive, so archive reads newest-first).
   - **ARCHITECTURE.md**: Update Implementation Sequence table status.
     Format: "Phase N complete" after each phase, or "Complete" if this was
     the module's final phase.
   - **DECISIONS.md**: Close any Open decisions resolved by this phase.
   - **PROJECT.md**: Close any Open risks resolved by this phase.
3. DEVLOG learning review — scan this phase's entries for trial-and-error
   patterns. Extract prescriptive one-liners and promote to DEVPLAN Gotchas.
4. Contract Changes scan — scan DEVLOG for Contract Changes markers. List
   affected upstream documents and flag what needs propagation.
5. Integration check — if this phase modified cross-module types or wired
   modules together, run `/integration-check` between affected module pairs.
   Verify actual outputs feed into actual inputs (not just fakes).
6. Make all updates identified in steps 2–5. Commit.
7. Present summary of everything done.

**If autonomous:** Commit. Exit with ESCALATE — human audits before next
phase begins.
**If supervised:** Do not commit. Wait for explicit confirmation.
