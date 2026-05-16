"""Core cost accountant implementation."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from toolkit.cost_accountant.errors import UnknownModelError
from toolkit.cost_accountant.types import (
    DEFAULT_PRICING,
    BatchEstimate,
    CallEstimate,
    CostEstimate,
    LedgerEntry,
    ModelPricing,
)
from toolkit.llm_client import Message


class CostAccountant:
    """Track and enforce LLM call costs against session-local budgets."""

    def __init__(
        self,
        ledger_path: Path,
        pricing: Optional[Dict[str, ModelPricing]] = None,
    ):
        self.ledger_path = Path(ledger_path)
        self.pricing = dict(DEFAULT_PRICING if pricing is None else pricing)
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
        """Estimate cost for one call from token counts."""
        if model not in self.pricing:
            raise UnknownModelError(model)

        pricing = self.pricing[model]
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
