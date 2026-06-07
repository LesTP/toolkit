# Extraction Plan — `edit_classifier`

> Coordinated cross-project change. Cannot be done autonomously by either
> project's worker loop because the diplomat-side import-path swap must
> happen in the same session that creates the toolkit module, otherwise
> diplomat's tests break.
>
> Drafted 2026-06-07 from Diplomat → Toolkit extraction analysis. Sibling
> precedent: `coaching` extraction (2026-06-05, see `ARCH_coaching.md`).

## Goal

Move the `LLMEditClassifier` primitive from `diplomat/src/modules/edit_classifier/`
to `toolkit/src/toolkit/edit_classifier/` so both Diplomat and Clanker Courts
can consume it. Satisfies the second-consumer rule: Clanker Courts is
incoming (per its `PROJECT.md` — has a Diplomat head producing bilateral
messages and an operator coaching surface mirroring Diplomat's `coached_game.py`
pattern).

## What moves vs stays project-side

**Moves to toolkit (~190 LOC):**
- `LLMEditClassifier` class — pure LLM-as-categorical-judge primitive
- `EditClassification` dataclass (`category, confidence, rationale, classifier_model, classified_at`)
- `EDIT_CLASSIFICATION_SCHEMA` — JSON schema enforcing the six categories
- `EDIT_CLASSIFICATION_CATEGORIES` — the six-tuple constant
  (`tone_softer, tone_harder, commitment_removed, ambiguity_added,
  constraint_enforcement, persona_correction`)
- `_build_user_prompt(original, edited, edit_notes)` — schema-shaped prompt assembler
- `_resolve_classifier_model(llm_config, tier)` — picks the model name from the LLM config dict

**Stays project-side (one thin factory per consumer):**
- `build_edit_classifier(llm_client, llm_providers_config, tier, attribution)` —
  reads Diplomat's `pipeline.yaml` `{"primary": {...}, "secondary": {...}}`
  shape, calls toolkit's `LLMEditClassifier(...)`. Lives at
  `diplomat/src/modules/edit_classifier/__init__.py`.
- Same shape on Clanker Courts side once that project consumes the module.
- `_subsystem_llm_config(primary, tier)` — diplomat-specific config translator.
  Already duplicated from `modules.reconciliation`; both copies should call
  the existing `subsystem_llm_config` helper instead.

**Stays project-side per project:**
- `config/prompts/edit_classifier.txt` — the prompt text. Diplomat's mentions
  "diplomatic response", "faction voice", "national interests". Clanker
  Courts will write its own with five-of-six categories unchanged and minor
  wording tweaks for the graph-game context.

## Pinned design decisions

These were settled 2026-06-07 in the diplomat session and do not need
re-litigating during extraction.

- **D-X1: Six categories stay hardcoded as a tuple constant in toolkit.**
  Both Diplomat and Clanker Courts use the same six per analysis (five
  translate verbatim, `constraint_enforcement` covers game-rule constraints
  in both). Revisit only when a third consumer wants a different category
  list, at which point parameterize via constructor kwarg.
- **D-X2: Factory lives project-side, not in toolkit.** Toolkit exports only
  the primitive (`LLMEditClassifier`, `EditClassification`, schema, categories).
  Each project writes its own `build_edit_classifier(...)` adapter that
  reads its own config-file convention and calls the toolkit constructor.
  Rationale: toolkit primitives stay pure of project-specific config
  assumptions. Matches the existing `build_reconciler` precedent (lives in
  `diplomat/src/modules/reconciliation/__init__.py` and wraps toolkit's
  `structured_call`).
- **D-X3: `load_prompt` stays inlined.** It's a one-liner (`Path(p).read_text(encoding="utf-8").strip()`).
  Promote to a `toolkit.io` module only when there are 3+ callers.
- **D-X4: `DEFAULT_PROMPT_PATH` removed from toolkit.** The current
  hardcoded `Path("config/prompts/edit_classifier.txt")` is meaningless at
  toolkit level (each project has its own filesystem). Toolkit constructor
  takes `prompt_path` as a required kwarg.

## Steps (do all in one human-driven session — both repos)

| # | Step | Where |
|---|---|---|
| 1 | Create `toolkit/src/toolkit/edit_classifier/` with `__init__.py`, `classifier.py`, `types.py`. Copy from diplomat; strip `from modules.extraction import load_prompt` and inline the one-liner; remove `DEFAULT_PROMPT_PATH`; remove `_subsystem_llm_config` (project concern); remove `build_edit_classifier` (project concern). | toolkit |
| 2 | Add toolkit `__init__.py` to re-export the four public names: `EditClassification`, `LLMEditClassifier`, `EDIT_CLASSIFICATION_SCHEMA`, `EDIT_CLASSIFICATION_CATEGORIES`. | toolkit |
| 3 | Copy `tests/test_edit_classifier.py` to `toolkit/tests/edit_classifier/` (mirror existing per-module test directory layout). Adjust imports to `from toolkit.edit_classifier import ...`. Drop tests that exercised `build_edit_classifier` (factory test stays in diplomat). 4–5 tests should remain at toolkit level. | toolkit |
| 4 | Create `toolkit/ARCH_edit_classifier.md` matching the `ARCH_coaching.md` shape — provenance line, public API, schema, categories enum, usage example. Mention second-consumer rule satisfied by Clanker Courts (incoming). | toolkit |
| 5 | Add toolkit `DECISIONS.md` entries D-X1 through D-X4 verbatim from this plan. | toolkit |
| 6 | Update toolkit reference docs with the new module. Each has a different shape — mirror the existing `coaching` entries for tone:<br>**`PROJECT.md`** — add `edit_classifier` to the Modules list (one line, mirror the coaching line at PROJECT.md:24). Add a Change-History row noting the extraction date + second-consumer satisfied by Clanker Courts (mirror coaching's PROJECT.md:76 row).<br>**`README.md`** — add a `### toolkit.edit_classifier` section (description, import example, usage snippet showing `LLMEditClassifier(...).classify(original, edited, edit_notes)`). Mirror the per-module section style used for `### toolkit.coaching`.<br>**`API.md`** — add a `## toolkit.edit_classifier` section with class signature for `LLMEditClassifier`, the `EditClassification` dataclass, the schema dict, and the categories tuple. Mirror coaching's API.md section.<br>**`TOOLKIT_REFERENCE.md`** — add one row to "Modules at a glance" table (`\| toolkit.edit_classifier \| from toolkit.edit_classifier import ... \| LLM-as-judge categorical classifier ... \|`) AND a per-module section further down (mirror the coaching section).<br>**`.llms/rules/toolkit.md`** — add one bullet to the Available Modules list (mirror coaching's bullet at line 28: `- Edit Classifier — LLM-as-judge categorical classifier for review-gate edit logs (ARCH_edit_classifier.md)`).<br>**`VALIDATION_NOTES.md`** — add a section listing the cross-project consumer expectation (Diplomat verified; Clanker Courts incoming). | toolkit |
| 7 | Run toolkit tests: `pytest toolkit/tests/edit_classifier -q` — must be green. | toolkit |
| 8 | Diplomat side: replace `src/modules/edit_classifier/classifier.py` and `types.py` with re-export wrappers OR delete them and update `src/modules/edit_classifier/__init__.py` to: (a) `from toolkit.edit_classifier import EditClassification, LLMEditClassifier, EDIT_CLASSIFICATION_CATEGORIES, EDIT_CLASSIFICATION_SCHEMA`, (b) keep diplomat's `build_edit_classifier(...)` factory locally with the existing `_subsystem_llm_config` adapter. | diplomat |
| 9 | Update diplomat callers that import classifier internals directly (check `tools/classify_edit_log.py`, `tests/test_edit_classifier_regression.py`, orchestrator wiring). All should go through the diplomat package's `__init__.py` so the toolkit import is the only path change. | diplomat |
| 10 | Run diplomat full suite: `pytest -q` from diplomat root. Expect identical pass count (~388 tests after Phase 33). One test for the factory stays diplomat-side; all primitive tests now run from toolkit. | diplomat |
| 11 | Update diplomat docs: `ARCH_review_gate.md` (note classifier now from toolkit), `ARCH_coaching.md` "Review Gate Edit Log → Prompt Refinement" section (same), `ARCHITECTURE.md` Component Map row, `diplomat-testing-doc.md` §7.3 (mention toolkit module). Mirror the wording style used in `ARCHITECTURE.md` row for `Coaching` post-extraction (`"... extracted to toolkit.coaching 2026-06-05"`). | diplomat |
| 12 | Diplomat single commit message: `"Consume edit_classifier from toolkit (extract primitive; factory + prompt stay project-side)"`. Toolkit commits separately as needed (likely one for module + tests, one for ARCH + DECISIONS, one for cross-doc updates). | both |

## Files affected

**Toolkit (new):**
```
toolkit/src/toolkit/edit_classifier/__init__.py
toolkit/src/toolkit/edit_classifier/classifier.py
toolkit/src/toolkit/edit_classifier/types.py
toolkit/tests/edit_classifier/test_classifier.py  (or similar)
toolkit/ARCH_edit_classifier.md
```

**Toolkit (updated):**
```
toolkit/DECISIONS.md          — add D-X1..D-X4
toolkit/PROJECT.md            — Modules list entry + Change-History row
toolkit/README.md             — new `### toolkit.edit_classifier` per-module section
toolkit/API.md                — new `## toolkit.edit_classifier` section
toolkit/TOOLKIT_REFERENCE.md  — Modules at a glance table row + per-module section
toolkit/.llms/rules/toolkit.md — Available Modules bullet
toolkit/VALIDATION_NOTES.md   — cross-project consumer expectation entry
```

**Diplomat (updated):**
```
diplomat/src/modules/edit_classifier/__init__.py    — re-export from toolkit + keep factory
diplomat/src/modules/edit_classifier/classifier.py  — DELETED (or shrunk to factory only)
diplomat/src/modules/edit_classifier/types.py       — DELETED (toolkit owns the dataclass)
diplomat/ARCH_review_gate.md                        — note toolkit dependency
diplomat/ARCH_coaching.md                           — note toolkit dependency in feedback-loop section
diplomat/ARCHITECTURE.md                            — Component Map row update
diplomat/diplomat-testing-doc.md                    — §7.3 reference toolkit module
```

**Diplomat (unchanged):**
```
diplomat/config/prompts/edit_classifier.txt         — prompt stays diplomat-local
diplomat/tools/classify_edit_log.py                 — imports unchanged (go through diplomat package)
diplomat/tests/test_edit_classifier_regression.py   — imports unchanged (project-side path)
diplomat/src/orchestrator.py                        — already imports diplomat's package, no change
```

## Verification

- Toolkit: `pytest toolkit/tests/edit_classifier -q` → expect ~4–5 passing
- Diplomat: `pytest -q` from diplomat root → expect 388 passing (same as post-Phase 33 baseline). If count drops, a project-side test was lost in the migration.
- Live smoke (optional): exercise diplomat's `tools/classify_edit_log.py --db ...` against an existing `review_gate_edits` row with `action='edited'`. Should produce the same `category/confidence/rationale` shape as before.

## Risk

**Low.** Same shape as the `coaching` extraction that landed cleanly 2026-06-05 with no follow-up issues. Two concerns to verify pre-merge:

1. Diplomat's `tools/classify_edit_log.py` and `tests/test_edit_classifier_regression.py` may import classifier internals directly (bypassing the package `__init__.py`). Pre-flight `grep -RIn 'from modules.edit_classifier.classifier' tests tools` to catch this; fix to go through the package.
2. The factory keeps diplomat's `_subsystem_llm_config` helper. Verify it still matches the corresponding helper in `modules.reconciliation` (they were intentional duplicates per the earlier session — confirm they haven't drifted).

## Out of scope

- Parameterizing the six categories. Deferred to a third-consumer trigger per D-X1.
- Promoting `load_prompt` to a `toolkit.io` module. Deferred per D-X3.
- Adding a `toolkit.llm_judge` rename / generalization. The classifier stays domain-named (`edit_classifier`) until a non-edit categorical-judge use case appears.
- Clanker Courts' factory implementation. That gets written when Clanker Courts wires the classifier in — separate session, only affects clankercourts repo.

## Sequencing

Do this **before** Clanker Courts starts depending on the classifier. The longer Clanker Courts goes without it, the more pressure there will be to duplicate the module rather than wait on extraction.

Best done in a focused human session (~1–2 hours) since:
- It touches three repos (toolkit, diplomat, eventually clankercourts)
- A worker loop can't atomically coordinate a cross-repo change
- The diplomat test suite must be re-run after the import swap

## Cross-reference once landed

After completion, update:
- This file → move/rename to `EXTRACTION_LOG_edit_classifier.md` or fold into toolkit `DEVLOG.md`
- Diplomat `ARCHITECTURE.md` Implementation Sequence row referring to "Edit Classifier" with `(extracted to toolkit.edit_classifier YYYY-MM-DD)` annotation
- Toolkit `README.md` module list
