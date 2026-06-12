# ARCH: LLM Client

## Purpose
Provider-agnostic interface for LLM API calls. Supports multiple providers (Anthropic, OpenAI, Google, OpenRouter), model tiers (quality vs. commodity), rate-limit tracking, and multi-provider subscription rotation. Simple consumers use a single provider with one call; complex consumers use the full routing and budget features. Adapted from TGBot's `src/summarization/client.py`.

## Public API

### complete
- **Signature:** `complete(messages: list[Message], config: LLMConfig, tier: ModelTier = ModelTier.DEFAULT) -> LLMResponse`
- **Parameters:**
  - messages: list[Message] — conversation messages
    ```python
    @dataclass
    class Message:
        role: str       # "system", "user", "assistant"
        content: str
    ```
  - config: LLMConfig — provider configuration (see below)
  - tier: ModelTier — which quality level to use. The router maps tiers to specific models.
    ```python
    class ModelTier(str, Enum):
        QUALITY = "quality"       # best available model (distillation, generation)
        DEFAULT = "default"       # good general-purpose model
        COMMODITY = "commodity"   # cheapest adequate model (pre-fetch scoring, parsing)
    ```
- **Returns:** LLMResponse
- **Errors:**
  - `LLMAPIError` — API call failed (auth, network, server error). Includes provider, status, and retry info.
  - `LLMRateLimitError(LLMAPIError)` — rate limit hit. Includes retry_after_seconds if available.
  - `LLMResponseError` — API returned successfully but response was empty or unparseable.
  - `LLMProviderError` — unknown provider name in config.

### complete_with_rotation
- **Signature:** `complete_with_rotation(messages: list[Message], configs: list[LLMConfig], tier: ModelTier = ModelTier.DEFAULT) -> LLMResponse`
- **Parameters:**
  - messages: same as `complete`
  - configs: list[LLMConfig] — ordered list of provider configs to try. On rate limit or failure from the first, falls through to the next.
  - tier: same as `complete`
- **Returns:** LLMResponse (from whichever provider succeeded)
- **Errors:**
  - `LLMAllProvidersExhaustedError` — all providers in the list failed or are rate-limited. Includes per-provider error details.

### get_budget_status
- **Signature:** `get_budget_status(config: LLMConfig) -> BudgetStatus`
- **Parameters:**
  - config: LLMConfig — the provider to check
- **Returns:** BudgetStatus with remaining capacity estimate
- **Errors:** None (returns unknown status if tracking unavailable)

## Configuration

```python
@dataclass
class LLMConfig:
    provider: str               # "anthropic", "openai", "google", "openrouter"
    api_key: str
    models: dict[str, str]      # tier name → model identifier
    max_tokens: int = 4096      # default max response tokens
    temperature: float = 0.7    # default temperature
    budget_tracker: BudgetTracker | None = None  # optional usage tracking

@dataclass
class BudgetStatus:
    provider: str
    tokens_used_today: int
    estimated_tokens_remaining: int | None  # None if unknown
    rate_limit_resets_at: datetime | None    # None if not rate-limited
    status: str                              # "ok", "approaching_limit", "rate_limited"
```

Example configs:
```python
# Simple (TGBot-style): single provider, two tiers
simple_config = LLMConfig(
    provider="anthropic",
    api_key="sk-...",
    models={
        "quality": "claude-sonnet-4-5-20250929",
        "commodity": "claude-haiku-4-5-20251001",
    },
)

# Complex (Phosphene-style): multiple providers for rotation
configs = [
    LLMConfig(provider="anthropic", api_key="sk-ant-...",
              models={"quality": "claude-opus-...", "default": "claude-sonnet-...", "commodity": "claude-haiku-..."}),
    LLMConfig(provider="openai", api_key="sk-oai-...",
              models={"quality": "gpt-5.4", "default": "gpt-5.4-mini", "commodity": "gpt-5.4-nano"}),
]
```

## Provider Abstraction

```python
class LLMProvider(ABC):
    @abstractmethod
    def call(self, model: str, messages: list[Message], max_tokens: int,
             temperature: float) -> LLMResponse: ...

    @abstractmethod
    def get_usage(self) -> dict: ...
```

- `AnthropicProvider` — wraps the `anthropic` Python SDK (adapted from TGBot)
- `OpenAIProvider` — wraps the `openai` Python SDK
- `GoogleProvider` — wraps the `google-genai` Python SDK
- `OpenRouterProvider` — wraps OpenRouter's OpenAI-compatible API
- `create_provider(config: LLMConfig) -> LLMProvider` — factory dispatching on `config.provider`

Adding a provider: implement `LLMProvider`, add a branch to `create_provider`. No consumer changes.

### Token-parameter dispatch (OpenAIProvider)

OpenAI's reasoning-family models (`gpt-5*`, `o1*`, `o3*`, `o4*`) reject the legacy `max_tokens` parameter with a 400 and require `max_completion_tokens` instead. The non-reasoning models (`gpt-4*`, `gpt-3.5*`) keep accepting `max_tokens`.

`OpenAIProvider.call()` dispatches on a lowercase model-prefix check and sends the matching kwarg to `chat.completions.create()`. Consumers of `LLMProvider.call()` pass `max_tokens: int` unchanged — the OpenAI-side translation is internal. Contract pinned by `TestOpenAIProviderTokenParam` in `tests/llm_client/test_core.py`.

If OpenAI introduces another prefix that requires `max_completion_tokens`, extend the prefix tuple in `OpenAIProvider.call()`. No changes needed in `LLMProvider`, `create_provider`, or consumers.

### Reasoning-content fallback (OpenRouterProvider)

Several reasoning models routed via OpenRouter (`deepseek/deepseek-r1`, `deepseek/deepseek-r1-distill-llama-70b`, `qwen/qwen3-*`, and likely others) return their answer in the response's `reasoning` or `reasoning_content` field with the standard `content` field empty or `None`. OpenAI's own o-series via OpenRouter's OpenAI passthrough does NOT have this issue — only non-OpenAI backends.

`OpenRouterProvider.call()` falls back to `reasoning` / `reasoning_content` when `content` is empty, before raising `LLMResponseError`. This prevents `complete_with_retry`'s `retry_on_empty=True` default from silently retrying empty-content responses indefinitely (the failure mode that hung Diplomat Run 17's R1 cells for an hour).

**Caveat for consumers.** When the fallback fires, `LLMResponse.content` is the model's thinking text (which the model would otherwise wrap in `<think>...</think>` tags). Downstream JSON parsers / `structured_call` extractors should tolerate first-person reasoning prose ("Okay, let me think about this..."). Content takes precedence when populated, so non-reasoning models and OpenAI-backed reasoning models are unaffected.

Contract pinned by three tests in `TestOpenRouterProvider`: `test_empty_content_falls_back_to_reasoning_field`, `test_empty_content_falls_back_to_reasoning_content_field`, `test_content_takes_precedence_over_reasoning`.

## Outputs

```python
@dataclass
class LLMResponse:
    content: str            # generated text
    model: str              # model identifier actually used
    provider: str           # provider name
    token_usage: TokenUsage
    latency_ms: int         # wall-clock time for the API call

@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
```

## State
- **Rate-limit state:** per-provider, in-memory. Tracks last rate-limit response and reset time. Resets on process restart.
- **Budget tracker (optional):** if `BudgetTracker` is provided in config, accumulates token usage across calls within a time window (e.g., daily). Persisted to a JSON file by the consumer (toolkit provides the interface, consumer provides the storage path).
- No other state. Each `complete()` call is independent.

## Usage Example
```python
from llm_client import complete, complete_with_rotation, LLMConfig, ModelTier, Message

config = LLMConfig(
    provider="anthropic",
    api_key="sk-...",
    models={"quality": "claude-sonnet-4-5-20250929", "commodity": "claude-haiku-4-5-20251001"},
)

# Simple call (TGBot style)
response = complete(
    messages=[
        Message(role="system", content="You are a technical writer."),
        Message(role="user", content="Summarize this README: ..."),
    ],
    config=config,
    tier=ModelTier.COMMODITY,
)
print(f"{response.model}: {response.content[:100]}...")
print(f"Tokens: {response.token_usage.input_tokens} in, {response.token_usage.output_tokens} out")

# Rotation call (Phosphene style)
response = complete_with_rotation(
    messages=[Message(role="user", content="Synthesize these observations: ...")],
    configs=[anthropic_config, openai_config, google_config],
    tier=ModelTier.QUALITY,
)
print(f"Served by: {response.provider}/{response.model}")
```
