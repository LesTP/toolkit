"""Cost accountant error hierarchy."""


class CostAccountantError(Exception):
    """Base class for cost accountant errors."""


class BudgetExceededError(CostAccountantError):
    """Estimated cost exceeds a configured budget."""

    def __init__(self, message: str, estimated_cost_usd: float, budget_usd: float):
        super().__init__(message)
        self.estimated_cost_usd = estimated_cost_usd
        self.budget_usd = budget_usd


class PerCallBudgetError(BudgetExceededError):
    """A single estimated LLM call exceeds the per-call budget."""


class OperationBudgetError(BudgetExceededError):
    """Estimated operation cumulative spend exceeds the operation budget."""


class SessionBudgetError(BudgetExceededError):
    """Estimated session cumulative spend exceeds the session budget."""


class SpendingCapAbortError(CostAccountantError):
    """The LLM API reported that an account spending cap was reached."""


class RateLimitAbortError(CostAccountantError):
    """The LLM API reported rate limiting and the call should abort."""


class UnknownModelError(CostAccountantError):
    """Model pricing was requested for an unknown model."""

    def __init__(self, model: str):
        super().__init__(f"Unknown model pricing: {model!r}")
        self.model = model
