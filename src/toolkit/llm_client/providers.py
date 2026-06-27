"""
LLM provider abstraction and implementations.

Defines LLMProvider ABC for provider-agnostic LLM access,
AnthropicProvider as the concrete implementation, and a
factory function to create providers from config.
"""

import random
import time
from abc import ABC, abstractmethod

from toolkit.llm_client.types import (
    LLMAPIError,
    LLMConfig,
    LLMResponse,
    LLMResponseError,
    Message,
    ModelTier,
    TokenUsage,
)


def _json_mode_prompt(prompt: str) -> str:
    """Append an OpenAI-compatible JSON mode hint to the prompt."""
    if not prompt:
        return "Return only valid json."
    return f"{prompt}\n\nReturn only valid json."


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Each provider normalizes its API's response into an LLMResponse.
    """

    @abstractmethod
    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Call the LLM and return a structured response.

        Raises:
            LLMAPIError: API call failed (rate limit, auth, network).
            LLMResponseError: API returned but response is empty or unparseable.
        """


class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic API (Claude models)."""

    def __init__(self, api_key: str):
        try:
            import anthropic as _anthropic
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for AnthropicProvider. "
                "Install it with: pip install toolkit[anthropic]"
            )
        self._anthropic = _anthropic
        self._client = _anthropic.Anthropic(api_key=api_key)

    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> LLMResponse:
        messages = [{"role": "user", "content": user_prompt}]
        # Anthropic does not expose an OpenAI-style `response_format` knob.
        # When json_mode is requested, use the model's assistant-prefill path
        # instead of changing the shared provider contract. This is the
        # asymmetric branch documented for this phase.
        if json_mode:
            system_prompt = _json_mode_prompt(system_prompt)
            messages.append({"role": "assistant", "content": "{"})
        try:
            response = self._client.messages.create(
                model=model,
                system=system_prompt,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except self._anthropic.RateLimitError as e:
            retry_after = None
            retry_header = e.response.headers.get("retry-after")
            if retry_header is not None:
                try:
                    retry_after = float(retry_header)
                except (ValueError, TypeError):
                    pass
            raise LLMAPIError(
                str(e),
                status_code=e.status_code,
                retry_after=retry_after,
            ) from e
        except self._anthropic.APIStatusError as e:
            raise LLMAPIError(
                str(e),
                status_code=e.status_code,
            ) from e
        except self._anthropic.APIConnectionError as e:
            raise LLMAPIError(str(e)) from e

        if not response.content or not response.content[0].text\
                or not response.content[0].text.strip():
            raise LLMResponseError("Empty response content from Anthropic API")

        content = response.content[0].text
        if json_mode and not content.lstrip().startswith("{"):
            content = "{" + content

        return LLMResponse(
            content=content,
            model=response.model,
            provider="anthropic",
            token_usage=TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )


class GeminiProvider(LLMProvider):
    """LLM provider backed by the Google Gemini API."""

    def __init__(self, api_key: str):
        try:
            from google import genai as _genai
        except ImportError:
            raise ImportError(
                "The 'google-genai' package is required for GeminiProvider. "
                "Install it with: pip install toolkit[google]"
            )
        self._genai = _genai
        self._client = _genai.Client(api_key=api_key)

    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> LLMResponse:
        try:
            generation_config_kwargs = {
                "system_instruction": system_prompt,
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            }
            if json_mode:
                generation_config_kwargs["response_mime_type"] = "application/json"
            response = self._client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=self._genai.types.GenerateContentConfig(
                    **generation_config_kwargs,
                ),
            )
        except self._genai.errors.ClientError as e:
            raise LLMAPIError(str(e)) from e
        except self._genai.errors.ServerError as e:
            raise LLMAPIError(str(e)) from e
        except Exception as e:
            raise LLMAPIError(str(e)) from e

        if not response.text or not response.text.strip():
            raise LLMResponseError("Empty response content from Gemini API")

        usage = response.usage_metadata
        return LLMResponse(
            content=response.text,
            model=model,
            provider="google",
            token_usage=TokenUsage(
                input_tokens=usage.prompt_token_count if usage else 0,
                output_tokens=usage.candidates_token_count if usage else 0,
            ),
        )


class OpenAIProvider(LLMProvider):
    """LLM provider backed by the OpenAI API (GPT models)."""

    def __init__(self, api_key: str):
        try:
            import openai as _openai
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for OpenAIProvider. "
                "Install it with: pip install toolkit[openai]"
            )
        self._openai = _openai
        self._client = _openai.OpenAI(api_key=api_key)

    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> LLMResponse:
        # Reasoning-family models (gpt-5.x, o1/o3/o4) differ from legacy
        # gpt-4.x / gpt-3.5 in two ways, both keyed off the model-name prefix:
        #   1. they require `max_completion_tokens` (not `max_tokens`);
        #   2. they reject any explicit `temperature` other than the API
        #      default of 1 — sending 0.7 returns a 400.
        # For these models we use the completion-token param and omit
        # `temperature` entirely (the API then applies its default of 1). All
        # other models keep the legacy behavior, so this is backwards-compatible.
        model_lower = model.lower()
        if model_lower.startswith(("gpt-5", "o1", "o3", "o4")):
            token_kwarg = {"max_completion_tokens": max_tokens}
            temperature_kwarg: dict = {}
        else:
            token_kwarg = {"max_tokens": max_tokens}
            temperature_kwarg = {"temperature": temperature}
        try:
            completion_kwargs = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": _json_mode_prompt(system_prompt)
                        if json_mode
                        else system_prompt,
                    },
                    {"role": "user", "content": user_prompt},
                ],
                **temperature_kwarg,
                **token_kwarg,
            }
            if json_mode:
                completion_kwargs["response_format"] = {"type": "json_object"}
            response = self._client.chat.completions.create(**completion_kwargs)
        except self._openai.RateLimitError as e:
            retry_after = None
            if e.response is not None:
                retry_header = e.response.headers.get("retry-after")
                if retry_header is not None:
                    try:
                        retry_after = float(retry_header)
                    except (ValueError, TypeError):
                        pass
            raise LLMAPIError(
                str(e),
                status_code=e.status_code,
                retry_after=retry_after,
            ) from e
        except self._openai.APIStatusError as e:
            raise LLMAPIError(
                str(e),
                status_code=e.status_code,
            ) from e
        except self._openai.APIConnectionError as e:
            raise LLMAPIError(str(e)) from e

        choice = response.choices[0] if response.choices else None
        if not choice or not choice.message or not choice.message.content\
                or not choice.message.content.strip():
            raise LLMResponseError("Empty response content from OpenAI API")

        usage = response.usage
        return LLMResponse(
            content=choice.message.content,
            model=response.model,
            provider="openai",
            token_usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )


class OpenRouterProvider(OpenAIProvider):
    """LLM provider backed by the OpenRouter OpenAI-compatible API."""

    def __init__(self, api_key: str):
        try:
            import openai as _openai
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for OpenRouterProvider. "
                "Install it with: pip install toolkit[openai]"
            )
        self._openai = _openai
        self._client = _openai.OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> LLMResponse:
        try:
            completion_kwargs = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": _json_mode_prompt(system_prompt)
                        if json_mode
                        else system_prompt,
                    },
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                completion_kwargs["response_format"] = {"type": "json_object"}
            response = self._client.chat.completions.create(**completion_kwargs)
        except self._openai.RateLimitError as e:
            retry_after = None
            if e.response is not None:
                retry_header = e.response.headers.get("retry-after")
                if retry_header is not None:
                    try:
                        retry_after = float(retry_header)
                    except (ValueError, TypeError):
                        pass
            raise LLMAPIError(
                str(e),
                status_code=e.status_code,
                retry_after=retry_after,
            ) from e
        except self._openai.APIStatusError as e:
            raise LLMAPIError(
                str(e),
                status_code=e.status_code,
            ) from e
        except self._openai.APIConnectionError as e:
            raise LLMAPIError(str(e)) from e

        choice = response.choices[0] if response.choices else None
        if not choice or not choice.message:
            raise LLMResponseError("Empty response content from OpenRouter API")

        # Prefer content; fall back to reasoning fields for models (e.g.,
        # DeepSeek R1, DeepSeek R1-distill, Qwen3, OpenRouter o1/o3/o4
        # routes via non-OpenAI backends) that return their answer in
        # `reasoning_content` / `reasoning` instead of `content`. Some
        # OpenRouter backends for reasoning models populate ONLY the
        # reasoning field, leaving content empty — without this fallback
        # the empty-content guard plus complete_with_retry's
        # retry_on_empty default produces a silent infinite-retry hang.
        # Note: when this fallback fires, the returned content is the
        # model's thinking, not a synthesized final answer. Downstream
        # parsers (structured_call, JSON extractors) may need to be
        # tolerant of think-step prose.
        content = choice.message.content
        if not content or not content.strip():
            content = (
                getattr(choice.message, "reasoning", None)
                or getattr(choice.message, "reasoning_content", None)
            )
        if not content or not content.strip():
            raise LLMResponseError("Empty response content from OpenRouter API")

        usage = response.usage
        return LLMResponse(
            content=content,
            model=response.model,
            provider="openrouter",
            token_usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )


def create_provider(config: LLMConfig) -> LLMProvider:
    """Create an LLM provider from config.

    Dispatches on config.provider. Currently supports "anthropic",
    "openai", "google", and "openrouter".

    Raises:
        ValueError: Unknown provider name.
    """
    if config.provider == "anthropic":
        return AnthropicProvider(api_key=config.api_key)
    if config.provider == "openai":
        return OpenAIProvider(api_key=config.api_key)
    if config.provider == "google":
        return GeminiProvider(api_key=config.api_key)
    if config.provider == "openrouter":
        return OpenRouterProvider(api_key=config.api_key)
    raise ValueError(
        f"Unknown LLM provider: {config.provider!r}. "
        f"Supported providers: anthropic, openai, google, openrouter"
    )


def complete(
    messages: list[Message],
    config: LLMConfig,
    tier: ModelTier = ModelTier.DEFAULT,
    *,
    attribution: str | None = None,
    purpose: str | None = None,
) -> LLMResponse:
    """High-level LLM call: resolve tier, split messages, call provider.

    Args:
        messages: Conversation messages. System messages become the system
            prompt; user messages become the user prompt.
        config: Provider configuration with tier→model mapping.
        tier: Quality tier to select the model.
        attribution: Optional caller label for upstream logging/observability.
        purpose: Optional semantic purpose label for caller-side routing.

    Returns:
        LLMResponse from the resolved provider and model.

    Raises:
        ValueError: If tier is not in config.models, or messages is empty.
        LLMAPIError: API call failed.
        LLMResponseError: API returned empty or unparseable response.
    """
    if not messages:
        raise ValueError("messages must be non-empty")

    tier_key = tier.value if isinstance(tier, ModelTier) else tier
    if tier_key not in config.models:
        available = ", ".join(sorted(config.models.keys()))
        raise ValueError(
            f"Tier {tier_key!r} not in config.models. "
            f"Available tiers: {available}"
        )

    model = config.models[tier_key]

    system_parts: list[str] = []
    user_parts: list[str] = []
    for msg in messages:
        if msg.role == "system":
            system_parts.append(msg.content)
        else:
            user_parts.append(msg.content)

    system_prompt = "\n\n".join(system_parts)
    user_prompt = "\n\n".join(user_parts) if user_parts else ""

    provider = create_provider(config)
    return provider.call(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        json_mode=config.json_mode,
    )


# ---------------------------------------------------------------------------
# Retry-with-backoff wrapper
# ---------------------------------------------------------------------------


# HTTP status codes that should NOT be retried. Everything else is treated as
# transient. 429 (rate limit) and 5xx (server error) are explicitly retryable.
# Network errors (status_code is None) are also retryable.
_NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404, 422})


def _is_retryable_api_error(exc: LLMAPIError) -> bool:
    """Determine if an LLMAPIError represents a transient failure.

    Retryable:
    - status_code is None (network/connection error)
    - status_code == 429 (rate limit)
    - status_code >= 500 (server error)

    Not retryable (client error):
    - 400, 401, 403, 404, 422 (bad request, auth, not found, validation)

    Other 4xx codes are treated as non-retryable by default.
    """
    if exc.status_code is None:
        return True
    if exc.status_code == 429:
        return True
    if exc.status_code >= 500:
        return True
    return False


def _compute_backoff_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter: float,
    retry_after: float | None,
) -> float:
    """Compute next-attempt delay in seconds.

    If retry_after is set (from a 429 response's Retry-After header), honor
    it with a small jitter added on top.

    Otherwise use exponential backoff: base_delay * 2^attempt + jitter.
    Capped at max_delay.
    """
    if retry_after is not None and retry_after > 0:
        return min(retry_after + random.uniform(0, jitter), max_delay)
    delay = base_delay * (2 ** attempt)
    delay += random.uniform(0, jitter * delay)
    return min(delay, max_delay)


def complete_with_retry(
    messages: list[Message],
    config: LLMConfig,
    tier: ModelTier = ModelTier.DEFAULT,
    *,
    attribution: str | None = None,
    purpose: str | None = None,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.25,
    retry_on_empty: bool = True,
) -> LLMResponse:
    """complete() with exponential backoff retry on transient failures.

    Wraps :func:`complete` with retry logic for the kind of transient
    failures that are common at scale: rate limits, server errors, network
    blips, and (optionally) empty responses from safety filters.

    Retries on:
    - LLMAPIError with status_code == 429 (rate limit)
    - LLMAPIError with status_code >= 500 (server error)
    - LLMAPIError with status_code is None (network error)
    - LLMResponseError (empty response — often transient, especially Gemini
      safety-filter cases). Set ``retry_on_empty=False`` to disable.

    Does NOT retry on:
    - LLMAPIError with status_code in {400, 401, 403, 404, 422} (client errors)
    - Other exceptions (e.g., ValueError from config issues)

    Honors the Retry-After header from API responses when present (Anthropic
    and OpenAI providers populate ``LLMAPIError.retry_after`` from the
    header). Otherwise uses exponential backoff with jitter.

    Args:
        messages: Conversation messages (same as :func:`complete`).
        config: Provider configuration.
        tier: Quality tier to select the model.
        attribution: Optional caller label forwarded to :func:`complete`.
        purpose: Optional semantic purpose label forwarded to :func:`complete`.
        max_attempts: Total attempts including the first call (default 3 —
            meaning up to 2 retries after the initial attempt).
        base_delay: Base delay for exponential backoff in seconds (default 1.0).
        max_delay: Cap on any single backoff delay in seconds (default 30.0).
        jitter: Random jitter added on top of computed delays as a fraction
            of the delay (default 0.25 = up to 25% jitter).
        retry_on_empty: If True (default), retry on LLMResponseError. Set
            False if you want empty responses to fail fast (e.g., when an
            empty response is itself informative for your caller).

    Returns:
        LLMResponse on success.

    Raises:
        LLMAPIError: Final attempt failed with a retryable or non-retryable
            API error.
        LLMResponseError: Final attempt returned empty (and retried if
            ``retry_on_empty``).
        ValueError: Config-level error (not retried).
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    last_exc: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return complete(
                messages,
                config,
                tier,
                attribution=attribution,
                purpose=purpose,
            )
        except LLMAPIError as exc:
            if not _is_retryable_api_error(exc):
                raise
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = _compute_backoff_delay(
                    attempt, base_delay, max_delay, jitter,
                    retry_after=exc.retry_after,
                )
                time.sleep(delay)
        except LLMResponseError as exc:
            if not retry_on_empty:
                raise
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = _compute_backoff_delay(
                    attempt, base_delay, max_delay, jitter,
                    retry_after=None,
                )
                time.sleep(delay)

    # All attempts exhausted; re-raise the last exception we saw.
    assert last_exc is not None  # invariant: loop must have produced exc
    raise last_exc
