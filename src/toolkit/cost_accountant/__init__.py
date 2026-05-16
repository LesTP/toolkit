"""
toolkit.cost_accountant — LLM cost tracking and budget enforcement.

Public API:
    CostAccountant       — ledger-backed LLM call accountant
    CostBudget           — per-call, operation, and session budget limits
    CostEstimate         — single-call cost estimate
    BatchEstimate        — batch cost estimate with per-call breakdown
    CallEstimate         — one labeled batch estimate item
    LedgerEntry          — append-only JSONL ledger row
    CostReport           — historical ledger report
    ModelPricing         — per-million-token model pricing
    DEFAULT_PRICING      — built-in model pricing table
"""

from toolkit.cost_accountant.core import CostAccountant
from toolkit.cost_accountant.errors import (
    BudgetExceededError,
    CostAccountantError,
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

__all__ = [
    "CostAccountant",
    "CostBudget",
    "CostEstimate",
    "BatchEstimate",
    "CallEstimate",
    "LedgerEntry",
    "CostReport",
    "ModelPricing",
    "DEFAULT_PRICING",
    "CostAccountantError",
    "BudgetExceededError",
    "PerCallBudgetError",
    "OperationBudgetError",
    "SessionBudgetError",
    "SpendingCapAbortError",
    "RateLimitAbortError",
    "UnknownModelError",
]
