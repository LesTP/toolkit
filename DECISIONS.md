# Toolkit — Decision Log

<!-- Record non-trivial design and implementation decisions here.
     Use the full template for genuine design forks with trade-offs.
     For reactive decisions during Refine work, a one-line note in
     the DEVLOG is sufficient — don't over-use this file.

     Once Closed, don't reopen unless new evidence appears. -->

<!-- Example entry:

D-1: [Decision Title]
Date: 2026-04-01 | Status: Open | Closed
Priority: Critical | Important | Nice-to-have
Decision: [What was chosen]
Rationale: [Why — including alternatives considered]
Revisit if: [Condition that would invalidate this decision]

-->

D-1: Rate limit detection in cost_accountant
Date: 2026-05-16 | Status: Closed
Priority: Important
Decision: Detect rate limit errors via `LLMAPIError.status_code == 429` or message containing "rate limit". No dedicated `LLMRateLimitError` class exists in llm_client — the ARCH spec references it but it was never added.
Rationale: ARCH_cost_accountant.md §Dependencies says to import `LLMRateLimitError` from llm_client, but llm_client/types.py has only `LLMAPIError` and `LLMResponseError`. Modifying llm_client is a cross-module change requiring ESCALATE, so detect rate limits via status_code and message on base `LLMAPIError` instead.
Revisit if: llm_client adds `LLMRateLimitError` subclass — then import and use it directly.

D-2: Prompt Regression runner dispatch is consumer-provided
Date: 2026-05-28 | Status: Closed
Priority: Important
Decision: Extract the generic prompt regression runner with a `module_caller` callback instead of carrying diplomat's hardcoded module dispatch into toolkit.
Rationale: Toolkit cannot depend on diplomat domain modules. Scenario loading, property evaluation, judging, and reporting are reusable, but calling extraction/generation/analyst/adversarial modules is consumer-specific wiring.
Revisit if: Multiple consumers converge on the same module dispatch schema and a small optional adapter becomes clearly reusable.

D-3: Structured LLM uses an injected client protocol
Date: 2026-05-28 | Status: Closed
Priority: Important
Decision: Extract structured LLM helpers as a leaf module that accepts an injected client with `complete(messages, config, tier)` rather than importing `toolkit.llm_client`.
Rationale: The duplicated diplomat pattern is reusable across consumers, but the toolkit module should remain independent and usable with fakes or consumer-owned LLM wrappers. This matches the prompt_regression injection pattern and preserves the no-cross-dependency rule.
Revisit if: Multiple modules need a shared formal protocol type and the project approves a shared type package or an explicit dependency.

D-4: edit_classifier categories are hardcoded
Date: 2026-06-07 | Status: Closed
Priority: Important
Decision: The six edit-classification categories (`tone_softer`, `tone_harder`, `commitment_removed`, `ambiguity_added`, `constraint_enforcement`, `persona_correction`) are hardcoded as a module-level `EDIT_CLASSIFICATION_CATEGORIES` tuple and embedded in `EDIT_CLASSIFICATION_SCHEMA`.
Rationale: Both Diplomat and Clanker Courts use the same six categories (five translate verbatim; `constraint_enforcement` covers game-rule violations in both domains). Parameterizing the category list now would be premature generalization for two consumers with identical needs.
Revisit if: A third consumer needs a different category list, OR Diplomat / Clanker Courts diverge on category vocabulary mid-flight. At that point parameterize via a constructor kwarg with the current tuple as the default.

D-5: edit_classifier factory lives project-side, not in toolkit
Date: 2026-06-07 | Status: Closed
Priority: Important
Decision: Toolkit exports only the `LLMEditClassifier` primitive plus `EditClassification`, `EDIT_CLASSIFICATION_SCHEMA`, and `EDIT_CLASSIFICATION_CATEGORIES`. Each consumer writes its own `build_edit_classifier(...)` factory that reads its own config-file shape and constructs the primitive.
Rationale: Diplomat's `build_edit_classifier` reads a `pipeline.yaml`-shaped `{"primary": {...}, "secondary": {...}}` dict. Clanker Courts will have a different config layout. Baking diplomat's `"primary"` key assumption into toolkit would couple Clanker Courts' config to a diplomat convention. The project-side factory pattern matches the existing `build_reconciler` precedent (`diplomat/src/modules/reconciliation/__init__.py` wraps `toolkit.structured_llm.structured_call`).
Revisit if: Consumers' config conventions converge enough that a shared factory becomes obviously reusable. Until then, the ~15-line per-project adapter is the right cost-of-decoupling.

D-6: edit_classifier `load_prompt` stays inlined
Date: 2026-06-07 | Status: Closed
Priority: Routine
Decision: The prompt-loading helper (`Path(p).read_text(encoding="utf-8").strip()`) is inlined in `LLMEditClassifier.__init__` rather than imported from a `toolkit.io` helper module.
Rationale: One line. No existing `toolkit.io` module. Promoting to a shared helper requires creating the module and convincing 2+ other call sites to consume it; the cost-of-abstraction exceeds the cost-of-duplication at one caller.
Revisit if: Three or more toolkit modules need the same `read_text + strip` helper, at which point introduce `toolkit.io.load_prompt`.

D-7: edit_classifier constructor requires explicit `prompt_path` (no default)
Date: 2026-06-07 | Status: Closed
Priority: Routine
Decision: `LLMEditClassifier.__init__` takes `prompt_path: str | Path` as a required parameter. Diplomat's original `DEFAULT_PROMPT_PATH = Path("config/prompts/edit_classifier.txt")` constant was dropped in extraction.
Rationale: Toolkit cannot know the consumer's filesystem layout. A diplomat-relative default is meaningless from Clanker Courts (or from a test process with a different CWD). Each consumer's `build_*` factory passes its own path.
Revisit if: Toolkit grows a notion of consumer-relative paths (e.g. a `TOOLKIT_PROMPT_DIR` env var convention). Not on the roadmap.

D-8: clankmates_client scopes to player-side + generic helpers; host-side ops deferred
Date: 2026-06-10 | Status: Closed
Priority: Important
Decision: Phase 4 (this iteration) implements steps 4.1, 4.3, 4.4, 4.5 only: player-side subprocess wrapper (vendored), message decoders, thread-cursor store, and peer-DM screener. Host-side ops (step 4.2: `post_publish`, `channel_create`, typed-inbox schema management) are deferred until `p:\shared\diplomat\CLANKMATES_NOTES.md` exists (arena Phase A output, which documents the exact CLI surface for host-side commands). Step 4.6 (governance + integration check) defers until 4.2 ships and arena Phase C contract is firm.
Rationale: Host-side ops require confirming exact `clankm` subcommand flags against a live host session (arena Phase A). Implementing against speculative flags risks a breaking rework when the actual surface is confirmed. Player-side ops are fully validated in the upstream player-client test suite and can be vendored safely now. Both consumers (Diplomat arena, Clanker Courts game_transport) need the player-side + generic helpers immediately.
Revisit if: Arena Phase A completes and `CLANKMATES_NOTES.md` is written — then queue 4.2 in DEVPLAN.
