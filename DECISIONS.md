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
