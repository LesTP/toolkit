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
