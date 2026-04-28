"""
toolkit.llm_client — provider-agnostic LLM client.

Public API:
    complete        — high-level: messages + config + tier → LLMResponse
    Message         — conversation message (role, content)
    ModelTier       — quality tier enum (QUALITY, DEFAULT, COMMODITY)
    LLMConfig       — provider + credentials + model tier mapping
    LLMResponse     — structured response (content, model, provider, token_usage)
    TokenUsage      — input/output token counts
    LLMAPIError     — API call failed
    LLMResponseError — empty or unparseable response
    LLMProvider     — abstract base class for providers
    AnthropicProvider — Anthropic (Claude) implementation
    OpenAIProvider  — OpenAI (GPT) implementation
    GeminiProvider  — Google Gemini implementation
    create_provider — factory: config → provider instance
"""

from toolkit.llm_client.providers import (
    AnthropicProvider,
    GeminiProvider,
    LLMProvider,
    OpenAIProvider,
    complete,
    create_provider,
)
from toolkit.llm_client.types import (
    LLMAPIError,
    LLMConfig,
    LLMResponse,
    LLMResponseError,
    Message,
    ModelTier,
    TokenUsage,
)

__all__ = [
    "complete",
    "Message",
    "ModelTier",
    "LLMConfig",
    "LLMResponse",
    "TokenUsage",
    "LLMAPIError",
    "LLMResponseError",
    "LLMProvider",
    "AnthropicProvider",
    "OpenAIProvider",
    "GeminiProvider",
    "create_provider",
]
