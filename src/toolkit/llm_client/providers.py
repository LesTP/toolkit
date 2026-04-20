"""
LLM provider abstraction and implementations.

Defines LLMProvider ABC for provider-agnostic LLM access,
AnthropicProvider as the concrete implementation, and a
factory function to create providers from config.
"""

from abc import ABC, abstractmethod

from toolkit.llm_client.types import LLMAPIError, LLMConfig, LLMResponse, LLMResponseError


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
    ) -> LLMResponse:
        try:
            response = self._client.messages.create(
                model=model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=max_tokens,
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

        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            provider="anthropic",
            token_usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
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
    ) -> LLMResponse:
        try:
            response = self._client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=self._genai.types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=max_tokens,
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
            token_usage={
                "input_tokens": usage.prompt_token_count if usage else 0,
                "output_tokens": usage.candidates_token_count if usage else 0,
            },
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
    ) -> LLMResponse:
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
            )
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
            token_usage={
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
            },
        )


def create_provider(config: LLMConfig) -> LLMProvider:
    """Create an LLM provider from config.

    Dispatches on config.provider. Currently supports "anthropic",
    "openai", and "google".

    Raises:
        ValueError: Unknown provider name.
    """
    if config.provider == "anthropic":
        return AnthropicProvider(api_key=config.api_key)
    if config.provider == "openai":
        return OpenAIProvider(api_key=config.api_key)
    if config.provider == "google":
        return GeminiProvider(api_key=config.api_key)
    raise ValueError(
        f"Unknown LLM provider: {config.provider!r}. "
        f"Supported providers: anthropic, openai, google"
    )
