# Governance

Development process for asynchronous, multi-session collaboration with a stateless partner (AI or otherwise). Governing constraint: **minimize wasted work when each session starts cold.**

Documentation is the source of truth — do not rely on prior conversations. If something is ambiguous, **ask** (don't guess). Prioritize clarity over speed.

---

## Concepts

### Work Regimes

Work falls along a spectrum based on **evaluability** — who can assess whether the output is correct.

**Build (AI-evaluable):** Correctness verifiable by tests, type checks, or objective criteria.
- Tests and acceptance criteria specified **before** implementation
- Large work chunks (full phases)
- Decisions are architectural and durable

Examples: data models, algorithms, parsers, API contracts, integration wiring, build config.

When a module's tests use fakes or stubs for real external dependencies, at least one probe exercising the real interface must pass before phase-complete is accepted. Fakes that have never been checked against the real implementation encode assumptions, not contracts. See `/dependency-probe`.

**Refine (human-evaluable):** Correctness requires human perception or subjective judgment.
- Goals and constraints specified upfront; steps emerge iteratively
- Small increments shown to human frequently
- Decisions are reactive and may reverse

Feedback loop: Show → React → Triage (fix now / fix later / needs decision) → Adjust → Repeat

Examples: visual design, interaction feel, audio quality, layout, naming, copy.

**Explore (decision-evaluable):** Goal is to make a decision, not produce shipping code.
- Output: a closed decision (using the decision template)
- Method: prototype alternatives, compare, evaluate
- Time-boxed (one session or explicit limit)

Examples: technology selection, A/B comparisons, architecture alternatives.

**Identifying the regime:** Ask "Can the implementer verify this is correct without showing it to someone?"
- Yes → Build. Specify deeply: functions, test cases, step-by-step plan.
- No → Refine. Specify goals and constraints only. Do NOT pre-specify values that depend on perception.
- Need to decide first → Explore. Time-box it, produce a decision, then Build or Refine.

Most features pass through multiple regimes: Explore → Build → Refine. Plan for the transitions.

### Work Modes

Each session operates in one mode at a time:

**1. Discuss (no code changes)**
- Determine scope, identify the work regime, specify accordingly
- Prioritize simplest solutions; check if existing code can be reused/extended
- Preserve existing architecture unless there's a clear reason to change it
- If context is missing, ask before proceeding
- **Ends with** a DEVPLAN update

**2. Code / Debug**
- **Code:** implement the plan from the discuss session
- **Debug:** propose a testable hypothesis first, then make changes
- Switching between code and debug within a session is expected

**3. Review**
- Goal: improve existing code, not write new features
- **Priority #1:** preserve existing functionality
- **Priority #2:** simplify and reduce code
- Confirm architecture alignment (no drift from spec)

---

## Workflow

### Entry to Implementation

Implementation begins when Discovery and Architecture are complete.

**Prerequisites:**
- PROJECT.md exists (scope, audience, constraints, success criteria)
- ARCHITECTURE.md exists (component map, data flow, implementation sequence)
- For multi-module projects: ARCH_[module].md exists for each module

**First steps:**
1. Load PROJECT.md and ARCHITECTURE.md
2. Pick the first module from the implementation sequence
3. Create its DEVPLAN (see Documentation Formats below)
4. Enter Discuss mode

### Phase Lifecycle

#### Planning (Discuss mode)

1. Determine scope and specific outcomes
2. Identify work regime (Build / Refine / Explore)
3. Specify accordingly:
   - **Build:** break into smallest testable steps; create test specs
   - **Refine:** define goals, constraints, and first item to show; skip detailed step plans
   - **Explore:** define the decision to be made and time box
4. Update DEVPLAN

**Refine phase structure:**

| Stage | Focus | Content |
|-------|-------|---------|
| First | Goals & constraints | What "good" looks like, hard limits |
| Middle | Feedback loops | Iterative show→adjust cycles (count unknown upfront) |
| Last | Stabilization | Lock decisions, write tests for final state, document |

For Refine phases, plan a **time budget**, not a step count.

If this is the first phase of a module, update the module's Status in ARCHITECTURE.md's Implementation Sequence table to "In progress".

#### Step Execution

1. **Discuss:** specific changes, files affected, decisions needed
2. **Code/Debug**
3. **Verify:** run tests (Build) or show to human (Refine)
4. **Update DEVLOG** (see Documentation Formats for entry format)
5. **Commit** — one commit per logical unit (see Commit Rules below)

#### Phase Review

Review all code from the current phase.

**Priority #1:** Preserve existing functionality.
**Priority #2:** Simplify and reduce code.

Check for:
- Dead code or unused imports
- Architecture drift from the spec
- Opportunities to simplify

Organize findings as:
- **Must fix** (correctness, architecture violations)
- **Should fix** (simplification, cleanup)
- **Optional** (style, minor improvements)

#### Phase Completion

1. Run phase-level tests (Build) or human sign-off (Refine)
2. If any fakes cover real external dependencies, confirm a dependency probe has passed for each (see `/dependency-probe`)
3. Apply remaining review fixes
4. **DEVLOG learning review** — scan this phase's DEVLOG entries for trial-and-error patterns. Extract prescriptive one-liners and promote to DEVPLAN Gotchas.
5. **Contract scan** — scan DEVLOG for Contract Changes markers. Propagate to upstream documents.
6. **DEVPLAN cleanup** — reduce completed phase to a one-line summary with DEVLOG reference. Archive the previous phase's DEVLOG entries to `DEVLOG_archive.md`.
7. Update module Status in ARCHITECTURE.md's Implementation Sequence table.
8. Set DEVPLAN frontmatter: `blocked: true`. The `/close` bot command (or human) clears the gate by setting `blocked: false`.

---

## Rules

### Commits

**Commit vs. amend:** Default to NEW commit. Only amend when explicitly asked.

**Cadence:** One commit per logical unit, not per session.

### Scope

**Scope expansion:** When scope grows mid-session, acknowledge it explicitly. Add to the list (do now) or defer. Log additions in the DEVLOG. Don't silently absorb new work.

### Error Escalation

1. Diagnose and apply a targeted fix
2. Same error recurs — try a fundamentally different approach
3. Still failing — question assumptions, search for solutions, reconsider the plan
4. After three failures — stop and ask for guidance

### Contract Changes

**Contract-change markers:** When a DEVLOG entry modifies a shared contract, include a `### Contract Changes` section listing affected documents and specific contracts modified.

**Propagation rules:**
- **Immediate** (same session): Changes that modify a cross-module API signature or type. Test: "Would a cold-start session on another module produce incorrect code by reading the current ARCH doc?" If yes, propagate now.
- **Phase boundary** (batched): All other contract changes. At phase completion, scan DEVLOG's Contract Changes markers and update listed documents.

**Test propagation:** When a contract change crosses a module boundary that is already built, propagation includes test work:
1. Update the consumer's test double to match the new contract signature.
2. Run or add a boundary test that exercises the real producer through the consumer's call path.
3. Both updates land in the same commit as the contract change.

**Upstream revision protocol:**

*Scope changes (PROJECT.md):* Flexible scope changes can proceed inline. Core scope changes require pausing implementation and assessing impact against ARCHITECTURE.md.

*Architecture changes (ARCHITECTURE.md, ARCH files):* If a module boundary needs to move or a contract was fundamentally wrong:
1. Pause implementation on affected modules
2. Update ARCHITECTURE.md and affected ARCH files
3. Adjust implementation sequence if needed
4. Record the change as a decision (D-#) in DECISIONS.md
5. Resume implementation

### Session Habits

**Re-read before deciding.** Before any significant decision or direction change, re-read the DEVPLAN. Long sessions cause context drift.

**Don't re-read what you just wrote.** Only re-read when starting a new session or when the file may have been modified by another step.

---

## Documentation Formats

Every project maintains:

| File | Purpose | Update Timing |
|------|---------|---------------|
| **DEVPLAN.md** | Cold start context, roadmap, phase breakdown | Before each iteration |
| **DEVLOG.md** | What actually happened — changes, issues, lessons | After each iteration |

### DEVPLAN Structure

**Frontmatter** (YAML at the very top):
```yaml
---
phase: 3b
blocked: false
---
```

`blocked` is the single source of truth for whether work is gated. When `true`, no work should proceed until it is cleared to `false`.

Projects using autonomous execution add a `state` field — see WORKER_SPEC.md.

**Cold Start Summary** (stable — update on major shifts):
- **What this is** — one-sentence scope
- **Key constraints** — non-obvious technical limits
- **Gotchas** — operational knowledge learned through trial-and-error

**Current Status** (volatile — update after each step):
- **Phase** — e.g., "3b — Hit-test math"
- **Focus** — what's being built right now
- **Blocked/Broken** — anything preventing progress

**Cleanup rule:** When a phase completes, reduce its section to a one-line summary with a DEVLOG reference. The DEVPLAN should get *shorter* as work progresses.

### DEVLOG Entry Format

```markdown
### Step [N]: [short title]
- **Mode:** Code | Debug | Review | Discuss
- **Outcome:** complete | partial | blocked
- **Contract changes:** none | [list of affected documents]

[Free-form prose: what was done, decisions made, issues encountered]
```

**Archival rule:** DEVLOG is append-only — new entries go at the bottom (newest last). During phase completion, move the previous phase's entries to `DEVLOG_archive.md`. The active DEVLOG should contain only the current phase's entries.

### Decision Log

```
D-#: [Title]
Date: YYYY-MM-DD | Status: Open | Closed
Priority: Critical | Important | Nice-to-have
Decision:
Rationale:
Revisit if:
```

Once **Closed**, don't reopen unless new evidence appears. For reactive decisions during Refine work, a one-line "changed X because Y" in the DEVLOG is sufficient.

---

## Patterns

### Cross-Module Integration

Before integrating modules A and B:
1. **Type compatibility** — verify A's output types match B's input types
2. **Boundary tests** — feed A's actual outputs into B's actual functions
3. **Bridge logic** — document any adapter/conversion needed

### Sub-Track Pattern

When cross-cutting work grows beyond a few DEVLOG entries, spin it off into its own DEVPLAN/DEVLOG pair. **Naming:** `DEVPLAN_<TOPIC>.md` / `DEVLOG_<TOPIC>.md`.

### Structured Feedback Logging

When iterating visually (show → react → adjust), log each cycle in the DEVLOG:

```
1. [Observation] Transport row sticks out past other elements
   Hypothesis: flex-wrap causing wrap when scrollbar appears
   Fix: removed flex-wrap
   Result: ✗ — scrollbar still steals layout width
2. [Root cause found] Native scrollbar steals 15px
   Fix: thin 6px custom scrollbar + flex-shrink
   Result: ✓ — resolved
```
