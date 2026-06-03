"""Tests for toolkit.llm_client — types, complete(), and provider abstraction."""

import pytest

from toolkit.llm_client import (
    LLMAPIError,
    LLMConfig,
    LLMProvider,
    LLMResponse,
    LLMResponseError,
    Message,
    ModelTier,
    TokenUsage,
    complete,
    complete_with_retry,
    create_provider,
)


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class TestMessage:
    def test_construction(self):
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"

    def test_system_role(self):
        msg = Message(role="system", content="you are helpful")
        assert msg.role == "system"

    def test_assistant_role(self):
        msg = Message(role="assistant", content="sure")
        assert msg.role == "assistant"


# ---------------------------------------------------------------------------
# ModelTier
# ---------------------------------------------------------------------------


class TestModelTier:
    def test_values(self):
        assert ModelTier.QUALITY.value == "quality"
        assert ModelTier.DEFAULT.value == "default"
        assert ModelTier.COMMODITY.value == "commodity"

    def test_is_string_enum(self):
        assert isinstance(ModelTier.QUALITY, str)
        assert ModelTier.QUALITY == "quality"

    def test_from_string(self):
        assert ModelTier("quality") is ModelTier.QUALITY
        assert ModelTier("commodity") is ModelTier.COMMODITY


# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_construction(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50

    def test_in_response(self):
        response = LLMResponse(
            content="hello",
            model="test-model",
            provider="test",
            token_usage=TokenUsage(input_tokens=10, output_tokens=20),
        )
        assert response.token_usage.input_tokens == 10
        assert response.token_usage.output_tokens == 20


# ---------------------------------------------------------------------------
# LLMConfig
# ---------------------------------------------------------------------------


class TestLLMConfig:
    def test_model_property(self):
        config = LLMConfig(
            provider="anthropic",
            api_key="sk-test",
            models={"quality": "claude-opus", "commodity": "claude-haiku"},
        )
        assert config.model == "claude-opus"

    def test_model_property_empty(self):
        config = LLMConfig(provider="anthropic", api_key="sk-test")
        with pytest.raises(ValueError, match="models is empty"):
            _ = config.model

    def test_tier_key_access(self):
        config = LLMConfig(
            provider="anthropic",
            api_key="sk-test",
            models={
                "quality": "claude-opus",
                "default": "claude-sonnet",
                "commodity": "claude-haiku",
            },
        )
        assert config.models[ModelTier.QUALITY] == "claude-opus"
        assert config.models[ModelTier.DEFAULT] == "claude-sonnet"
        assert config.models[ModelTier.COMMODITY] == "claude-haiku"

    def test_defaults(self):
        config = LLMConfig(provider="test", api_key="key")
        assert config.max_tokens == 4096
        assert config.temperature == 0.7


# ---------------------------------------------------------------------------
# Stub provider for complete() tests
# ---------------------------------------------------------------------------


class StubProvider(LLMProvider):
    """Records calls and returns canned responses."""

    def __init__(self):
        self.calls: list[dict] = []

    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self.calls.append({
            "model": model,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        return LLMResponse(
            content="stub response",
            model=model,
            provider="stub",
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
        )


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------


class TestComplete:
    def _config(self, **overrides):
        defaults = dict(
            provider="anthropic",
            api_key="sk-test",
            models={
                "quality": "claude-opus",
                "default": "claude-sonnet",
                "commodity": "claude-haiku",
            },
            max_tokens=1000,
            temperature=0.5,
        )
        defaults.update(overrides)
        return LLMConfig(**defaults)

    def test_tier_resolution(self, monkeypatch):
        stub = StubProvider()
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: stub,
        )
        config = self._config()
        complete(
            [Message(role="user", content="hi")],
            config,
            tier=ModelTier.QUALITY,
        )
        assert stub.calls[0]["model"] == "claude-opus"

    def test_default_tier(self, monkeypatch):
        stub = StubProvider()
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: stub,
        )
        config = self._config()
        complete([Message(role="user", content="hi")], config)
        assert stub.calls[0]["model"] == "claude-sonnet"

    def test_system_user_split(self, monkeypatch):
        stub = StubProvider()
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: stub,
        )
        config = self._config()
        complete(
            [
                Message(role="system", content="be helpful"),
                Message(role="user", content="question"),
            ],
            config,
        )
        assert stub.calls[0]["system_prompt"] == "be helpful"
        assert stub.calls[0]["user_prompt"] == "question"

    def test_multiple_system_messages_joined(self, monkeypatch):
        stub = StubProvider()
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: stub,
        )
        config = self._config()
        complete(
            [
                Message(role="system", content="rule one"),
                Message(role="system", content="rule two"),
                Message(role="user", content="go"),
            ],
            config,
        )
        assert stub.calls[0]["system_prompt"] == "rule one\n\nrule two"

    def test_user_only_no_system(self, monkeypatch):
        stub = StubProvider()
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: stub,
        )
        config = self._config()
        complete([Message(role="user", content="just this")], config)
        assert stub.calls[0]["system_prompt"] == ""
        assert stub.calls[0]["user_prompt"] == "just this"

    def test_temperature_passthrough(self, monkeypatch):
        stub = StubProvider()
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: stub,
        )
        config = self._config(temperature=0.3)
        complete([Message(role="user", content="hi")], config)
        assert stub.calls[0]["temperature"] == 0.3

    def test_max_tokens_passthrough(self, monkeypatch):
        stub = StubProvider()
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: stub,
        )
        config = self._config(max_tokens=2000)
        complete([Message(role="user", content="hi")], config)
        assert stub.calls[0]["max_tokens"] == 2000

    def test_returns_response(self, monkeypatch):
        stub = StubProvider()
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: stub,
        )
        config = self._config()
        result = complete([Message(role="user", content="hi")], config)
        assert isinstance(result, LLMResponse)
        assert result.content == "stub response"
        assert isinstance(result.token_usage, TokenUsage)

    def test_missing_tier_raises(self):
        config = self._config(models={"quality": "opus"})
        with pytest.raises(ValueError, match="commodity"):
            complete(
                [Message(role="user", content="hi")],
                config,
                tier=ModelTier.COMMODITY,
            )

    def test_empty_messages_raises(self):
        config = self._config()
        with pytest.raises(ValueError, match="non-empty"):
            complete([], config)

    def test_string_tier_key_works(self, monkeypatch):
        """ModelTier is a str enum, so config.models["quality"] works."""
        stub = StubProvider()
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: stub,
        )
        config = LLMConfig(
            provider="anthropic",
            api_key="sk-test",
            models={"quality": "opus", "default": "sonnet"},
        )
        # Pass the enum — it should resolve via .value
        complete(
            [Message(role="user", content="hi")],
            config,
            tier=ModelTier.QUALITY,
        )
        assert stub.calls[0]["model"] == "opus"


# ---------------------------------------------------------------------------
# create_provider — error path
# ---------------------------------------------------------------------------


class TestCreateProvider:
    def test_unknown_provider_raises(self):
        config = LLMConfig(provider="unknown", api_key="key")
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_provider(config)

    def test_openrouter_factory_returns_openrouter_provider(self):
        """create_provider("openrouter") returns OpenRouterProvider.

        Verifies the step-30.2 factory branch without a live API call.
        The sys.modules mock from _make_mock_openai() (module-level) makes
        OpenRouterProvider constructible even without the openai package.
        """
        import importlib
        import toolkit.llm_client.providers as _mod
        importlib.reload(_mod)
        from toolkit.llm_client.providers import OpenRouterProvider

        config = LLMConfig(provider="openrouter", api_key="or-test-key")
        provider = create_provider(config)
        assert isinstance(provider, OpenRouterProvider)


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class TestErrors:
    def test_api_error_fields(self):
        err = LLMAPIError("rate limited", status_code=429, retry_after=30.0)
        assert str(err) == "rate limited"
        assert err.status_code == 429
        assert err.retry_after == 30.0

    def test_api_error_defaults(self):
        err = LLMAPIError("fail")
        assert err.status_code is None
        assert err.retry_after is None

    def test_response_error(self):
        err = LLMResponseError("empty")
        assert str(err) == "empty"

    def test_api_error_is_exception(self):
        with pytest.raises(LLMAPIError):
            raise LLMAPIError("test")

    def test_response_error_is_exception(self):
        with pytest.raises(LLMResponseError):
            raise LLMResponseError("test")


# ---------------------------------------------------------------------------
# complete_with_retry
# ---------------------------------------------------------------------------


class FlakeyProvider(LLMProvider):
    """Provider that raises a configured sequence of exceptions, then succeeds.

    The exceptions list is consumed front-to-back. If an entry is None, that
    attempt returns a successful response. If the list is exhausted, all
    further calls succeed.
    """

    def __init__(self, exceptions: list[Exception | None]):
        self._exceptions = list(exceptions)
        self.call_count = 0

    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self.call_count += 1
        if self._exceptions:
            exc = self._exceptions.pop(0)
            if exc is not None:
                raise exc
        return LLMResponse(
            content="ok",
            model=model,
            provider="stub",
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )


def _retry_config() -> LLMConfig:
    return LLMConfig(
        provider="stub",
        api_key="key",
        models={"default": "test-model"},
    )


def _no_sleep(monkeypatch):
    """Patch time.sleep so retries don't actually wait during tests."""
    monkeypatch.setattr(
        "toolkit.llm_client.providers.time.sleep",
        lambda _: None,
    )


class TestCompleteWithRetry:
    def test_succeeds_on_first_try(self, monkeypatch):
        _no_sleep(monkeypatch)
        provider = FlakeyProvider([])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        result = complete_with_retry(
            [Message(role="user", content="hi")], _retry_config()
        )
        assert result.content == "ok"
        assert provider.call_count == 1

    def test_accepts_attribution_and_purpose(self, monkeypatch):
        _no_sleep(monkeypatch)
        provider = FlakeyProvider([])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        result = complete_with_retry(
            [Message(role="user", content="hi")],
            _retry_config(),
            attribution="alpha",
            purpose="generation",
        )
        assert result.content == "ok"
        assert provider.call_count == 1

    def test_retries_on_429(self, monkeypatch):
        _no_sleep(monkeypatch)
        provider = FlakeyProvider([
            LLMAPIError("rate limited", status_code=429, retry_after=0.01),
            None,
        ])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        result = complete_with_retry(
            [Message(role="user", content="hi")], _retry_config()
        )
        assert result.content == "ok"
        assert provider.call_count == 2

    def test_retries_on_5xx(self, monkeypatch):
        _no_sleep(monkeypatch)
        provider = FlakeyProvider([
            LLMAPIError("server error", status_code=503),
            None,
        ])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        result = complete_with_retry(
            [Message(role="user", content="hi")], _retry_config()
        )
        assert provider.call_count == 2
        assert result.content == "ok"

    def test_retries_on_network_error(self, monkeypatch):
        """status_code=None means network error — should retry."""
        _no_sleep(monkeypatch)
        provider = FlakeyProvider([
            LLMAPIError("connection refused"),  # status_code=None
            None,
        ])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        result = complete_with_retry(
            [Message(role="user", content="hi")], _retry_config()
        )
        assert provider.call_count == 2
        assert result.content == "ok"

    def test_retries_on_empty_response(self, monkeypatch):
        _no_sleep(monkeypatch)
        provider = FlakeyProvider([
            LLMResponseError("empty"),
            None,
        ])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        result = complete_with_retry(
            [Message(role="user", content="hi")], _retry_config()
        )
        assert provider.call_count == 2
        assert result.content == "ok"

    def test_does_not_retry_on_empty_when_disabled(self, monkeypatch):
        _no_sleep(monkeypatch)
        provider = FlakeyProvider([LLMResponseError("empty")])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        with pytest.raises(LLMResponseError):
            complete_with_retry(
                [Message(role="user", content="hi")],
                _retry_config(),
                retry_on_empty=False,
            )
        assert provider.call_count == 1

    def test_does_not_retry_on_401(self, monkeypatch):
        _no_sleep(monkeypatch)
        provider = FlakeyProvider([
            LLMAPIError("unauthorized", status_code=401),
        ])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        with pytest.raises(LLMAPIError) as exc_info:
            complete_with_retry(
                [Message(role="user", content="hi")], _retry_config()
            )
        assert exc_info.value.status_code == 401
        assert provider.call_count == 1

    def test_does_not_retry_on_400(self, monkeypatch):
        _no_sleep(monkeypatch)
        provider = FlakeyProvider([
            LLMAPIError("bad request", status_code=400),
        ])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        with pytest.raises(LLMAPIError):
            complete_with_retry(
                [Message(role="user", content="hi")], _retry_config()
            )
        assert provider.call_count == 1

    def test_exhausts_all_attempts_and_raises_last(self, monkeypatch):
        _no_sleep(monkeypatch)
        provider = FlakeyProvider([
            LLMAPIError("rate 1", status_code=429),
            LLMAPIError("rate 2", status_code=429),
            LLMAPIError("rate 3 final", status_code=429),
        ])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        with pytest.raises(LLMAPIError) as exc_info:
            complete_with_retry(
                [Message(role="user", content="hi")], _retry_config(),
                max_attempts=3,
            )
        # Last attempt's exception is the one re-raised
        assert "rate 3 final" in str(exc_info.value)
        assert provider.call_count == 3

    def test_max_attempts_one_is_no_retry(self, monkeypatch):
        _no_sleep(monkeypatch)
        provider = FlakeyProvider([
            LLMAPIError("rate", status_code=429),
        ])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        with pytest.raises(LLMAPIError):
            complete_with_retry(
                [Message(role="user", content="hi")], _retry_config(),
                max_attempts=1,
            )
        assert provider.call_count == 1

    def test_max_attempts_zero_raises_value_error(self):
        with pytest.raises(ValueError):
            complete_with_retry(
                [Message(role="user", content="hi")], _retry_config(),
                max_attempts=0,
            )

    def test_honors_retry_after_header(self, monkeypatch):
        """When LLMAPIError has retry_after, sleep with that value."""
        sleep_calls: list[float] = []
        monkeypatch.setattr(
            "toolkit.llm_client.providers.time.sleep",
            lambda d: sleep_calls.append(d),
        )
        # Suppress jitter randomness by patching random.uniform to 0
        monkeypatch.setattr(
            "toolkit.llm_client.providers.random.uniform",
            lambda a, b: 0.0,
        )
        provider = FlakeyProvider([
            LLMAPIError("rate", status_code=429, retry_after=5.0),
            None,
        ])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        complete_with_retry(
            [Message(role="user", content="hi")], _retry_config(),
        )
        assert sleep_calls == [5.0]

    def test_exponential_backoff_without_retry_after(self, monkeypatch):
        sleep_calls: list[float] = []
        monkeypatch.setattr(
            "toolkit.llm_client.providers.time.sleep",
            lambda d: sleep_calls.append(d),
        )
        monkeypatch.setattr(
            "toolkit.llm_client.providers.random.uniform",
            lambda a, b: 0.0,
        )
        provider = FlakeyProvider([
            LLMAPIError("err", status_code=500),
            LLMAPIError("err", status_code=500),
            None,
        ])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        complete_with_retry(
            [Message(role="user", content="hi")], _retry_config(),
            max_attempts=3,
            base_delay=1.0,
        )
        # attempt 0 failed → delay = 1.0 * 2^0 = 1.0
        # attempt 1 failed → delay = 1.0 * 2^1 = 2.0
        assert sleep_calls == [1.0, 2.0]

    def test_delay_capped_at_max(self, monkeypatch):
        sleep_calls: list[float] = []
        monkeypatch.setattr(
            "toolkit.llm_client.providers.time.sleep",
            lambda d: sleep_calls.append(d),
        )
        monkeypatch.setattr(
            "toolkit.llm_client.providers.random.uniform",
            lambda a, b: 0.0,
        )
        provider = FlakeyProvider([
            LLMAPIError("err", status_code=500),
            None,
        ])
        monkeypatch.setattr(
            "toolkit.llm_client.providers.create_provider",
            lambda config: provider,
        )
        complete_with_retry(
            [Message(role="user", content="hi")], _retry_config(),
            base_delay=100.0,
            max_delay=5.0,
        )
        assert sleep_calls == [5.0]

    def test_value_error_not_retried(self, monkeypatch):
        """Config-level errors (e.g. tier not in models) must not be retried."""
        _no_sleep(monkeypatch)
        config = LLMConfig(
            provider="stub",
            api_key="key",
            models={"default": "m"},
        )
        # Tier "quality" not in models - complete() raises ValueError
        with pytest.raises(ValueError):
            complete_with_retry(
                [Message(role="user", content="hi")],
                config,
                tier=ModelTier.QUALITY,
            )


# ---------------------------------------------------------------------------
# OpenAIProvider.call() — model-prefix token-parameter dispatch
# ---------------------------------------------------------------------------


class TestOpenAIProviderTokenParam:
    """Pin the contract that OpenAIProvider.call() picks the right token-limit
    parameter name based on model prefix.

    OpenAI's reasoning-family models (gpt-5.x, o1, o3, o4) reject the legacy
    `max_tokens` parameter with a 400 and require `max_completion_tokens`
    instead; the non-reasoning models (gpt-4.x, gpt-3.5) keep accepting the
    legacy name. Without dispatch, any deployment on a reasoning model fails.
    """

    @staticmethod
    def _stub_openai_response():
        """Minimal OpenAI-shaped response object for the provider to unpack."""
        from types import SimpleNamespace
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2),
            model="recorded-by-stub",
        )

    def _provider_with_recorder(self):
        """Build an OpenAIProvider whose chat.completions.create() records kwargs."""
        from toolkit.llm_client.providers import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return self._stub_openai_response()

        provider._client.chat.completions.create = fake_create
        return provider, captured

    @pytest.mark.parametrize(
        "model",
        ["gpt-5-mini", "gpt-5.4-mini", "o1", "o1-mini", "o3-mini", "o4-mini"],
    )
    def test_reasoning_models_use_max_completion_tokens(self, model):
        provider, captured = self._provider_with_recorder()
        provider.call(
            model=model,
            system_prompt="sys",
            user_prompt="usr",
            max_tokens=2048,
        )
        assert captured.get("max_completion_tokens") == 2048
        assert "max_tokens" not in captured

    @pytest.mark.parametrize(
        "model",
        ["gpt-4.1-mini", "gpt-4o", "gpt-4", "gpt-3.5-turbo"],
    )
    def test_legacy_models_use_max_tokens(self, model):
        provider, captured = self._provider_with_recorder()
        provider.call(
            model=model,
            system_prompt="sys",
            user_prompt="usr",
            max_tokens=2048,
        )
        assert captured.get("max_tokens") == 2048
        assert "max_completion_tokens" not in captured


# ---------------------------------------------------------------------------
# OpenRouterProvider
# ---------------------------------------------------------------------------


def _make_mock_openai():
    """Build a minimal openai mock sufficient for OpenRouterProvider tests.

    The real 'openai' package may not be installed in all environments.
    We patch sys.modules so OpenRouterProvider.__init__ can import it.
    """
    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    if "openai" in sys.modules:
        return None  # real package available; no patching needed

    stub_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
        model="meta-llama/llama-3.3-70b-instruct",
    )

    fake_client = MagicMock()
    fake_client.base_url = SimpleNamespace(host="openrouter.ai")
    fake_client.chat.completions.create.return_value = stub_response

    fake_openai = MagicMock()
    fake_openai.OpenAI.return_value = fake_client
    # Exception hierarchy needed for except-clause matching in provider.call()
    fake_openai.RateLimitError = type("RateLimitError", (Exception,), {
        "status_code": 429, "response": None,
    })
    fake_openai.APIStatusError = type("APIStatusError", (Exception,), {
        "status_code": 500,
    })
    fake_openai.APIConnectionError = type("APIConnectionError", (Exception,), {})

    sys.modules["openai"] = fake_openai
    return fake_openai


# Patch at import time so the module-level import inside providers.py succeeds.
_MOCK_OPENAI = _make_mock_openai()


class TestOpenRouterProvider:
    """Pin the contract for OpenRouterProvider — OpenAI-compatible wrapper.

    Tests use sys.modules patching when the real 'openai' package is absent,
    which is expected in CI environments that don't install the optional dep.
    """

    @staticmethod
    def _stub_response(content: str = "hello"):
        from types import SimpleNamespace
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
            model="meta-llama/llama-3.3-70b-instruct",
        )

    def _make_provider(self):
        """Return (provider, captured_kwargs_dict) with create() intercepted."""
        import importlib
        import toolkit.llm_client.providers as _mod
        importlib.reload(_mod)  # pick up sys.modules patch
        from toolkit.llm_client.providers import OpenRouterProvider

        provider = OpenRouterProvider(api_key="or-test-key")
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return self._stub_response()

        provider._client.chat.completions.create = fake_create
        return provider, captured

    def test_constructor_uses_openrouter_base_url(self):
        import importlib
        import toolkit.llm_client.providers as _mod
        importlib.reload(_mod)
        from toolkit.llm_client.providers import OpenRouterProvider

        provider = OpenRouterProvider(api_key="or-test-key")
        assert provider._client.base_url.host == "openrouter.ai"

    def test_call_returns_llm_response_with_openrouter_provider(self):
        provider, _ = self._make_provider()
        response = provider.call(
            model="meta-llama/llama-3.3-70b-instruct",
            system_prompt="You are helpful.",
            user_prompt="Hello",
            max_tokens=100,
        )
        assert isinstance(response, LLMResponse)
        assert response.provider == "openrouter"
        assert response.content == "hello"

    def test_call_always_uses_max_tokens_not_max_completion_tokens(self):
        """OpenRouter handles reasoning internally — always use max_tokens."""
        provider, captured = self._make_provider()
        provider.call(
            model="deepseek/deepseek-v3",
            system_prompt="sys",
            user_prompt="usr",
            max_tokens=512,
        )
        assert captured.get("max_tokens") == 512
        assert "max_completion_tokens" not in captured

    def test_rate_limit_error_surfaces_as_llm_api_error(self):
        from types import SimpleNamespace
        import sys

        provider, _ = self._make_provider()
        openai_mod = sys.modules["openai"]

        class FakeRateLimitError(Exception):
            status_code = 429
            response = SimpleNamespace(headers={"retry-after": "30"})

        exc = FakeRateLimitError("rate limit")
        openai_mod.RateLimitError = FakeRateLimitError
        provider._openai = openai_mod

        provider._client.chat.completions.create = lambda **kw: (_ for _ in ()).throw(exc)

        with pytest.raises(LLMAPIError) as info:
            provider.call(
                model="meta-llama/llama-3.3-70b-instruct",
                system_prompt="s",
                user_prompt="u",
                max_tokens=50,
            )
        assert info.value.status_code == 429
        assert info.value.retry_after == 30.0

    def test_empty_response_raises_llm_response_error(self):
        from types import SimpleNamespace

        provider, _ = self._make_provider()

        def fake_create(**kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="  "))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=0),
                model="meta-llama/llama-3.3-70b-instruct",
            )

        provider._client.chat.completions.create = fake_create

        with pytest.raises(LLMResponseError):
            provider.call(
                model="meta-llama/llama-3.3-70b-instruct",
                system_prompt="s",
                user_prompt="u",
                max_tokens=50,
            )
