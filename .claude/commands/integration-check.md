---
name: integration-check
description: Cross-module integration verification before wiring modules together
---

Before integrating, verify the following between the modules specified:

1. **Type compatibility** — verify that the upstream module's output types
   match the downstream module's input types. List any mismatches.
2. **Boundary tests** — feed the upstream module's actual outputs into the
   downstream module's actual functions. Report pass/fail.
3. **Bridge logic** — if any adapter or conversion is needed between
   modules, document what it is and where it should live.

Also check:
- No module imports from the integration/orchestration layer
- No direct cross-imports between subsystems except shared types from
  upstream dependencies

Present findings before making any changes.
