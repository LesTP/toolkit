"""Cost accountant types and default model pricing."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ModelPricing:
    """Pricing in USD per million input and output tokens."""

    input_per_mtok: float
    output_per_mtok: float


DEFAULT_PRICING: Dict[str, ModelPricing] = {
    # Anthropic
    "claude-sonnet-4-20250514": ModelPricing(3.0, 15.0),
    "claude-sonnet-4-6": ModelPricing(3.0, 15.0),
    "claude-haiku-4-5": ModelPricing(0.25, 1.25),
    "claude-opus-4": ModelPricing(15.0, 75.0),
    # OpenAI
    "gpt-4.1": ModelPricing(2.0, 8.0),
    "gpt-4.1-mini": ModelPricing(0.4, 1.6),
    "gpt-4.1-nano": ModelPricing(0.1, 0.4),
    "gpt-4o": ModelPricing(2.5, 10.0),
    "gpt-4o-mini": ModelPricing(0.15, 0.6),
    "gpt-5.5": ModelPricing(2.0, 8.0),
    "gpt-5.4": ModelPricing(2.0, 8.0),
    "gpt-5.4-mini": ModelPricing(0.4, 1.6),
    "o3": ModelPricing(2.0, 8.0),
    "o3-mini": ModelPricing(1.1, 4.4),
    "o4-mini": ModelPricing(1.1, 4.4),
}


@dataclass
class CostBudget:
    """Budget limits for one named LLM operation."""

    operation_name: str
    operation_budget_usd: float
    session_budget_usd: float = 100.0
    per_call_max_usd: float = 1.0
    abort_on_rate_limit: bool = True
    abort_on_spending_cap: bool = True


@dataclass
class CostEstimate:
    """Estimated cost for one LLM call."""

    model: str
    input_tokens: int
    estimated_output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_usd: float


@dataclass
class CallEstimate:
    """Estimated cost for one labeled call in a batch."""

    label: str
    input_tokens: int
    estimated_cost_usd: float


@dataclass
class BatchEstimate:
    """Estimated cost for a batch of calls."""

    calls: List[CallEstimate] = field(default_factory=list)
    total_usd: float = 0.0


@dataclass
class LedgerEntry:
    """Append-only JSONL ledger entry for an attempted LLM call."""

    timestamp: str
    operation: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cumulative_session_usd: float
    budget_name: str
    budget_remaining_usd: float
    duration_ms: int
    success: bool
    error: Optional[str]


@dataclass
class CostReport:
    """Historical cost report built from ledger entries."""

    total_calls: int
    total_spend_usd: float
    by_operation: Dict[str, float] = field(default_factory=dict)
    by_model: Dict[str, float] = field(default_factory=dict)
    by_date: Dict[str, float] = field(default_factory=dict)
    anomalies: List[str] = field(default_factory=list)
