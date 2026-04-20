"""
toolkit.llm_client — provider-agnostic LLM client.

Public API:
    LLMConfig       — provider + credentials + model tier mapping
    LLMResponse     — structured response (content, model, provider, token_usage)
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
    create_provider,
)
from toolkit.llm_client.types import (
    LLMAPIError,
    LLMConfig,
    LLMResponse,
    LLMResponseError,
)

__all__ = [
    "LLMConfig",
    "LLMResponse",
    "LLMAPIError",
    "LLMResponseError",
    "LLMProvider",
    "AnthropicProvider",
    "OpenAIProvider",
    "GeminiProvider",
    "create_provider",
]
