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
