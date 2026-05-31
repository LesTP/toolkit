"""Core cost accountant implementation."""

import json
import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from toolkit.cost_accountant.errors import (
    BudgetExceededError,
    OperationBudgetError,
    PerCallBudgetError,
    RateLimitAbortError,
    SessionBudgetError,
    SpendingCapAbortError,
    UnknownModelError,
)
from toolkit.cost_accountant.types import (
    DEFAULT_PRICING,
    BatchEstimate,
    CallEstimate,
    CostBudget,
    CostEstimate,
    CostReport,
    LedgerEntry,
    ModelPricing,
)
from toolkit.llm_client import (
    LLMAPIError,
    LLMConfig,
    LLMResponse,
    Message,
    ModelTier,
    complete_with_retry as llm_complete,
)


# Regexes for stripping provider date-snapshot suffixes from model IDs.
#
# OpenAI uses ISO-style YYYY-MM-DD with dashes:
#   gpt-4.1-mini-2025-04-14 → strip "-2025-04-14"
#   gpt-4o-2024-08-06       → strip "-2024-08-06"
#
# Anthropic uses packed YYYYMMDD without dashes between Y/M/D:
#   claude-haiku-4-5-20251001 → strip "-20251001"
#   claude-sonnet-4-20250514  → strip "-20250514"
# (Note: some explicit dated Anthropic entries are kept in DEFAULT_PRICING
# for backwards compatibility; normalization is a fallback when the exact
# ID isn't in the table.)
#
# Google's Gemini uses short numeric suffixes like "-001"/"-002" (3 digits)
# which are NOT date-shaped and remain untouched.
#
# Without normalization, dated IDs miss every entry in DEFAULT_PRICING and
# the cost accountant falls back to the conservative $15/$75 default.
# Retroactive audit of Run 8 cost ledger: 6.9x overall overestimate driven
# almost entirely by this lookup miss (gpt-4.1-mini-2025-04-14 inflated 40x
# from $0.49 actual to $19.73 reported; gemini-2.5-flash 39x).
_OPENAI_DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")
_ANTHROPIC_PACKED_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")


def normalize_model_name(model: str) -> str:
    """Strip provider date-snapshot suffixes for pricing lookup.

    Handles two formats:
    - OpenAI ``-YYYY-MM-DD`` (e.g. ``gpt-4.1-mini-2025-04-14`` → ``gpt-4.1-mini``)
    - Anthropic ``-YYYYMMDD`` packed (e.g. ``claude-haiku-4-5-20251001`` → ``claude-haiku-4-5``)

    Google's Gemini ``-001``/``-002`` numeric suffixes are 3 digits and not
    date-shaped; they are left intact (the table has explicit entries per
    model variant).

    Strips at most one suffix; safe to call on already-normalized names.
    """
    result = _OPENAI_DATE_SUFFIX_RE.sub("", model)
    if result == model:
        result = _ANTHROPIC_PACKED_DATE_SUFFIX_RE.sub("", model)
    return result


class CostAccountant:
    """Track and enforce LLM call costs against session-local budgets."""

    def __init__(
        self,
        ledger_path: Path,
        pricing: Optional[Dict[str, ModelPricing]] = None,
        default_budget: Optional[CostBudget] = None,
    ):
        self.ledger_path = Path(ledger_path)
        self.pricing = dict(DEFAULT_PRICING if pricing is None else pricing)
        self.default_budget = default_budget or CostBudget(
            operation_name="default",
            operation_budget_usd=25.0,
            session_budget_usd=25.0,
            per_call_max_usd=2.0,
        )
        self._session_total = 0.0
        self._operation_totals: Dict[str, float] = {}

        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.touch(exist_ok=True)
        self._ledger_entries = self._load_ledger()

    def _append_entry(self, entry: LedgerEntry) -> None:
        """Append one ledger entry as a compact JSON object."""
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            json.dump(asdict(entry), handle, separators=(",", ":"))
            handle.write("\n")
        self._ledger_entries.append(entry)

    def _load_ledger(self) -> List[LedgerEntry]:
        """Load existing ledger entries from disk for reporting."""
        entries: List[LedgerEntry] = []
        with self.ledger_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                data = json.loads(stripped)
                entries.append(LedgerEntry(**data))
        return entries

    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        expected_output_tokens: int = 1000,
    ) -> CostEstimate:
        """Estimate cost for one call from token counts.

        Looks up pricing by ``model``, falling back to the normalized name
        (date-suffix stripped) when the exact ID isn't in the table. If
        neither hits, uses a conservative high-end default for budget
        safety. The ``model`` field of the returned estimate preserves the
        original string for ledger fidelity.
        """
        pricing = self.pricing.get(model)
        if pricing is None:
            normalized = normalize_model_name(model)
            if normalized != model:
                pricing = self.pricing.get(normalized)
        if pricing is None:
            # Fall back to the highest known pricing for budget safety.
            pricing = ModelPricing(input_per_mtok=15.0, output_per_mtok=75.0)
        input_cost_usd = input_tokens * pricing.input_per_mtok / 1_000_000
        output_cost_usd = (
            expected_output_tokens * pricing.output_per_mtok / 1_000_000
        )
        return CostEstimate(
            model=model,
            input_tokens=input_tokens,
            estimated_output_tokens=expected_output_tokens,
            input_cost_usd=input_cost_usd,
            output_cost_usd=output_cost_usd,
            total_usd=input_cost_usd + output_cost_usd,
        )

    def estimate_batch(
        self,
        model: str,
        calls: List[Dict[str, object]],
        expected_output_tokens_per_call: int = 1000,
    ) -> BatchEstimate:
        """Estimate costs for labeled calls with input character counts."""
        estimates: List[CallEstimate] = []
        total_usd = 0.0

        for call in calls:
            input_chars = int(call["input_chars"])
            input_tokens = input_chars // 4
            estimate = self.estimate_cost(
                model=model,
                input_tokens=input_tokens,
                expected_output_tokens=expected_output_tokens_per_call,
            )
            label = str(call.get("label", ""))
            estimates.append(
                CallEstimate(
                    label=label,
                    input_tokens=input_tokens,
                    estimated_cost_usd=estimate.total_usd,
                )
            )
            total_usd += estimate.total_usd

        return BatchEstimate(calls=estimates, total_usd=total_usd)

    def _estimate_input_tokens(self, messages: List[Message]) -> int:
        """Estimate input tokens from concatenated message content."""
        return sum(len(message.content) for message in messages) // 4

    def complete(
        self,
        *,
        messages: List[Message],
        config: LLMConfig,
        tier: ModelTier,
        budget: Optional[CostBudget] = None,
        attribution: Optional[str] = None,
        purpose: Optional[str] = None,
    ) -> LLMResponse:
        """Budget-check, execute, and ledger an LLM client completion."""
        budget = budget or self.default_budget
        model = self._resolve_model(config, tier)
        input_tokens = self._estimate_input_tokens(messages)
        estimate = self.estimate_cost(
            model=model,
            input_tokens=input_tokens,
            expected_output_tokens=config.max_tokens,
        )
        start = time.monotonic()

        try:
            self._check_budgets(budget, estimate)
        except BudgetExceededError as error:
            self._append_failure(
                budget=budget,
                model=model,
                input_tokens=input_tokens,
                duration_ms=self._duration_ms(start),
                error=error,
            )
            raise

        try:
            complete_kwargs = {}
            if attribution is not None:
                complete_kwargs["attribution"] = attribution
            if purpose is not None:
                complete_kwargs["purpose"] = purpose
            response = llm_complete(
                messages=messages,
                config=config,
                tier=tier,
                **complete_kwargs,
            )
        except Exception as error:
            self._append_failure(
                budget=budget,
                model=model,
                input_tokens=input_tokens,
                duration_ms=self._duration_ms(start),
                error=error,
            )
            if self._is_spending_cap_error(error) and budget.abort_on_spending_cap:
                raise SpendingCapAbortError(str(error)) from error
            if self._is_rate_limit_error(error) and budget.abort_on_rate_limit:
                raise RateLimitAbortError(str(error)) from error
            raise

        output_tokens = response.token_usage.output_tokens
        actual_cost = self.estimate_cost(
            model=response.model,
            input_tokens=response.token_usage.input_tokens,
            expected_output_tokens=output_tokens,
        ).total_usd
        self._session_total += actual_cost
        self._operation_totals[budget.operation_name] = (
            self._operation_totals.get(budget.operation_name, 0.0) + actual_cost
        )
        self._append_entry(
            LedgerEntry(
                timestamp=self._timestamp(),
                operation=budget.operation_name,
                model=response.model,
                input_tokens=response.token_usage.input_tokens,
                output_tokens=output_tokens,
                cost_usd=actual_cost,
                cumulative_session_usd=self._session_total,
                budget_name=budget.operation_name,
                budget_remaining_usd=self._operation_remaining(budget),
                duration_ms=self._duration_ms(start),
                success=True,
                error=None,
            )
        )
        return response

    @property
    def session_total(self) -> float:
        """Return spend accumulated by this accountant instance."""
        return self._session_total

    def report(self, since: Optional[datetime] = None) -> CostReport:
        """Build a cost report from persisted ledger entries."""
        entries = self._filter_entries(since)
        by_operation: Dict[str, float] = {}
        by_model: Dict[str, float] = {}
        by_date: Dict[str, float] = {}
        failure_counts: Dict[str, int] = {}
        anomalies: List[str] = []
        total_spend = 0.0

        for entry in entries:
            total_spend += entry.cost_usd
            by_operation[entry.operation] = (
                by_operation.get(entry.operation, 0.0) + entry.cost_usd
            )
            by_model[entry.model] = by_model.get(entry.model, 0.0) + entry.cost_usd
            by_date[entry.timestamp[:10]] = (
                by_date.get(entry.timestamp[:10], 0.0) + entry.cost_usd
            )

            if entry.duration_ms > 60_000:
                anomalies.append(
                    f"Long duration for {entry.operation}: {entry.duration_ms}ms"
                )
            if not entry.success:
                failure_counts[entry.operation] = (
                    failure_counts.get(entry.operation, 0) + 1
                )

        for operation, count in sorted(failure_counts.items()):
            if count >= 3:
                anomalies.append(
                    f"Repeated failures for {operation}: {count} failed calls"
                )

        return CostReport(
            total_calls=len(entries),
            total_spend_usd=total_spend,
            by_operation=by_operation,
            by_model=by_model,
            by_date=by_date,
            anomalies=anomalies,
        )

    def _resolve_model(self, config: LLMConfig, tier: ModelTier) -> str:
        tier_key = tier.value if isinstance(tier, ModelTier) else str(tier)
        if tier_key not in config.models:
            available = ", ".join(sorted(config.models.keys()))
            raise ValueError(
                f"Tier {tier_key!r} not in config.models. "
                f"Available tiers: {available}"
            )
        return config.models[tier_key]

    def _check_budgets(self, budget: CostBudget, estimate: CostEstimate) -> None:
        if estimate.total_usd > budget.per_call_max_usd:
            raise PerCallBudgetError(
                "Estimated call cost exceeds per-call budget",
                estimate.total_usd,
                budget.per_call_max_usd,
            )

        operation_total = self._operation_totals.get(budget.operation_name, 0.0)
        if operation_total + estimate.total_usd > budget.operation_budget_usd:
            raise OperationBudgetError(
                "Estimated operation cost exceeds operation budget",
                operation_total + estimate.total_usd,
                budget.operation_budget_usd,
            )

        if self._session_total + estimate.total_usd > budget.session_budget_usd:
            raise SessionBudgetError(
                "Estimated session cost exceeds session budget",
                self._session_total + estimate.total_usd,
                budget.session_budget_usd,
            )

    def _append_failure(
        self,
        *,
        budget: CostBudget,
        model: str,
        input_tokens: int,
        duration_ms: int,
        error: Exception,
    ) -> None:
        self._append_entry(
            LedgerEntry(
                timestamp=self._timestamp(),
                operation=budget.operation_name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=0,
                cost_usd=0.0,
                cumulative_session_usd=self._session_total,
                budget_name=budget.operation_name,
                budget_remaining_usd=self._operation_remaining(budget),
                duration_ms=duration_ms,
                success=False,
                error=str(error),
            )
        )

    def _operation_remaining(self, budget: CostBudget) -> float:
        return budget.operation_budget_usd - self._operation_totals.get(
            budget.operation_name,
            0.0,
        )

    def _duration_ms(self, start: float) -> int:
        return int((time.monotonic() - start) * 1000)

    def _timestamp(self) -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _is_rate_limit_error(self, error: Exception) -> bool:
        if isinstance(error, LLMAPIError) and error.status_code == 429:
            return True
        return "rate limit" in str(error).lower()

    def _is_spending_cap_error(self, error: Exception) -> bool:
        message = str(error).lower()
        return (
            "spending cap" in message
            or "usage limit" in message
            or "usage limits" in message
        )

    def _filter_entries(self, since: Optional[datetime]) -> List[LedgerEntry]:
        if since is None:
            return list(self._ledger_entries)

        threshold = since
        if threshold.tzinfo is None:
            threshold = threshold.replace(tzinfo=timezone.utc)

        entries: List[LedgerEntry] = []
        for entry in self._ledger_entries:
            timestamp = self._parse_timestamp(entry.timestamp)
            if timestamp is not None and timestamp >= threshold:
                entries.append(entry)
        return entries

    def _parse_timestamp(self, timestamp: str) -> Optional[datetime]:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
