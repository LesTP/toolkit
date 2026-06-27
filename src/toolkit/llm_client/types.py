"""
LLM client types: configuration, response, and error classes.

Extracted from TGBot's summarization module and generalized
for multi-consumer, multi-provider use.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """A single message in a conversation."""

    role: str  # "system", "user", "assistant"
    content: str


# ---------------------------------------------------------------------------
# Model tier
# ---------------------------------------------------------------------------


class ModelTier(str, Enum):
    """Quality tier for model selection."""

    QUALITY = "quality"  # best available (distillation, generation)
    DEFAULT = "default"  # good general-purpose
    COMMODITY = "commodity"  # cheapest adequate (parsing, scoring)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class LLMConfig:
    """Provider-agnostic LLM configuration.

    Args:
        provider: Provider name (e.g. "anthropic").
        api_key: API key for the provider.
        models: Tier name → model identifier mapping
            (e.g. {"quality": "claude-sonnet-...", "commodity": "claude-haiku-..."}).
        max_tokens: Default max response tokens.
        temperature: Default sampling temperature.
    """

    provider: str
    api_key: str
    models: dict[str, str] = field(default_factory=dict)
    max_tokens: int = 4096
    temperature: float = 0.7
    json_mode: bool = False

    @property
    def model(self) -> str:
        """Shorthand: return the first model in the mapping.

        Convenience for single-model configs.

        Raises:
            ValueError: If models is empty.
        """
        if not self.models:
            raise ValueError("LLMConfig.models is empty")
        return next(iter(self.models.values()))


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


@dataclass
class TokenUsage:
    """Token counts from an LLM API call."""

    input_tokens: int
    output_tokens: int


@dataclass
class LLMResponse:
    """Structured response from an LLM provider call."""

    content: str
    model: str
    provider: str
    token_usage: TokenUsage


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LLMAPIError(Exception):
    """LLM API call failed (rate limit, auth, network)."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        retry_after: Optional[float] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after


class LLMResponseError(Exception):
    """LLM API returned successfully but response was empty or unparseable."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
