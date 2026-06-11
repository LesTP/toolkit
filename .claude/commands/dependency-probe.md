# /dependency-probe — Verify Real External Dependency Interfaces

Verify that fakes and stubs match the real interfaces they stand in for. Run this before trusting test suites that use fakes for external dependencies.

**"External dependency"** = anything the worker cannot modify: third-party libraries, sibling libraries (e.g., `toolkit/`), APIs, services, filesystems with non-standard semantics. The test: does the autonomous agent control both sides of the interface? If no, it's external.

---

## When to Run

- At Architecture exit — identify which modules will need probes
- At start of first phase of any module with external dependencies
- Before phase-complete on any module that added or changed a fake

---

## Procedure

### 1. Inventory external dependencies

For the current module, list every external real dependency. For each one, state:
- What it is (library, API, service, sibling project)
- Where the module uses it (which files, which calls)

### 2. Identify fake assumptions

For each dependency, find the corresponding fake/stub/mock in the test suite. State what the fake assumes about the real interface:
- Method signatures and parameter types
- Return value shapes and types (string vs. enum, dict structure, etc.)
- Error behavior (what exceptions, what error formats)
- Data formats (JSON wrapping, encoding, case sensitivity)
- Initialization requirements (required kwargs, config objects)

### 3. Probe or spec

For each dependency:

**If the real dependency is available in this environment:**
Run a minimal probe — the smallest possible invocation with real inputs. Compare the real response against the fake's assumptions. Report:
- **Match:** fake assumption matches real behavior
- **Mismatch:** fake assumption does not match — this is a bug waiting to surface
- **Surprise:** real behavior has properties the fake doesn't model (rate limits, response wrapping, content filtering, etc.)

**If the real dependency is not available:**
Produce a probe spec: what to call, with what inputs, what to assert. The spec should be executable by a human or a future session with access to the real dependency.

### 4. Report findings

Write a DEVLOG entry:

```markdown
### Step [N]: Dependency Probe — [module name]
- **Mode:** Probe
- **Outcome:** [N matches, N mismatches, N unknown]
- **Contract changes:** [list any mismatches that require code changes]

#### [Dependency Name]
- **Fake location:** `tests/fakes/fake_xxx.py`
- **Status:** Match | Mismatch | Unknown
- [Detail: what was checked, what was found]

#### [Next Dependency]
...
```

**Do not fix mismatches.** Report them. The human or a subsequent coding step decides the fix. Mismatches are bugs — they should be tracked, not silently corrected during the probe.

---

## Scope

This command is for **real external** dependencies only. For internal module-to-module wiring, use `/integration-check`.
