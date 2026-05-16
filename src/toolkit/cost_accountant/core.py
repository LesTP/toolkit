"""Core cost accountant implementation."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from toolkit.cost_accountant.types import (
    DEFAULT_PRICING,
    LedgerEntry,
    ModelPricing,
)


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
