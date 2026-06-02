import json
import threading
import time
from datetime import datetime, timezone

import pytest

from toolkit.gateway import (
    DeliveryResult,
    FeedbackSignal,
    Gateway,
    GatewayConfig,
    OutboundMessage,
    PlatformConfig,
    PlatformConfigError,
)


class FakeTelegramClient:
    def __init__(self, config: PlatformConfig) -> None:
        self.bot_token = config.credentials["bot_token"]
        self.chat_id = config.params["chat_id"]
        self.sent_messages: list[dict] = []
        self.api_requests: list[dict] = []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None,
    ) -> int:
        self.sent_messages.append(
            {"chat_id": chat_id, "text": text, "reply_to": reply_to}
        )
        return 200 + len(self.sent_messages)

    async def request_api(self, method: str, payload: dict | None = None) -> dict:
        self.api_requests.append({"method": method, "payload": dict(payload or {})})
        return {"ok": True, "result": {"message_id": 500 + len(self.api_requests)}}


def _telegram_platform() -> PlatformConfig:
    return PlatformConfig(
        name="telegram",
        adapter_type="telegram",
        credentials={"bot_token": "test-token"},
        params={"chat_id": "12345", "poll_interval_seconds": 0.01},
        output_formats=["text", "markdown", "telegraph", "thread"],
    )


class PollingTelegramClient(FakeTelegramClient):
    def __init__(self, config: PlatformConfig) -> None:
        super().__init__(config)
        self.get_updates_calls: list[dict] = []
        self.update_batches: list[list[dict]] = [
            [
                {
                    "update_id": 10,
                    "message": {
                        "message_id": 77,
                        "date": 1_777_777_780,
                        "text": "hello gateway",
                        "from": {"id": 42, "username": "human"},
                        "reply_to_message": {"message_id": 55},
                    },
                }
            ]
        ]
        self.block = threading.Event()
        self.stopped = False

    async def get_updates(
        self,
        offset: int | None = None,
        timeout: int | None = None,
    ) -> list[dict]:
        self.get_updates_calls.append({"offset": offset, "timeout": timeout})
        if self.update_batches:
            return self.update_batches.pop(0)
        self.block.wait(timeout=0.05)
        return []

    async def stop_polling(self) -> None:
        self.stopped = True
        self.block.set()


def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached before timeout")


def test_telegram_adapter_constructs_client_through_injected_factory() -> None:
    created: list[PlatformConfig] = []

    def factory(config: PlatformConfig) -> FakeTelegramClient:
        created.append(config)
        return FakeTelegramClient(config)

    gateway = Gateway(
        GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
        lambda _: None,
        lambda _: None,
        _telegram_client_factory=factory,
    )

    adapter = gateway._adapters_by_platform["telegram"]

    assert created == [_telegram_platform()]
    assert adapter.client.bot_token == "test-token"
    assert adapter.client.chat_id == "12345"
    assert adapter.chat_id == "12345"


def test_telegram_adapter_sends_text_and_thread_messages_through_client() -> None:
    gateway = Gateway(
        GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
        lambda _: None,
        lambda _: None,
        _telegram_client_factory=FakeTelegramClient,
    )
    adapter = gateway._adapters_by_platform["telegram"]

    text_result = gateway.send(
        OutboundMessage(
            content="plain",
            platform="telegram",
            format="text",
            intent_tag="free_play",
        )
    )
    thread_result = gateway.send(
        OutboundMessage(
            content="threaded",
            platform="telegram",
            format="thread",
            reply_to="77",
            intent_tag="reply",
        )
    )

    assert text_result == DeliveryResult(
        success=True,
        platform="telegram",
        message_id="201",
    )
    assert thread_result == DeliveryResult(
        success=True,
        platform="telegram",
        message_id="202",
    )
    assert adapter.client.sent_messages == [
        {"chat_id": 12345, "text": "plain", "reply_to": None},
        {"chat_id": 12345, "text": "threaded", "reply_to": 77},
    ]
    assert gateway._recent_deliveries[("telegram", "202")].intent_tag == "reply"


def test_telegram_adapter_sends_markdown_with_parse_mode_and_reply_metadata() -> None:
    gateway = Gateway(
        GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
        lambda _: None,
        lambda _: None,
        _telegram_client_factory=FakeTelegramClient,
    )
    adapter = gateway._adapters_by_platform["telegram"]

    result = gateway.send(
        OutboundMessage(
            content="*rich*",
            platform="telegram",
            format="markdown",
            reply_to="42",
            metadata={"parse_mode": "Markdown", "disable_web_page_preview": True},
        )
    )

    assert result == DeliveryResult(
        success=True,
        platform="telegram",
        message_id="501",
    )
    assert adapter.client.api_requests == [
        {
            "method": "sendMessage",
            "payload": {
                "chat_id": 12345,
                "text": "*rich*",
                "disable_web_page_preview": True,
                "reply_to_message_id": 42,
                "parse_mode": "Markdown",
            },
        }
    ]


def test_telegram_adapter_sends_telegraph_format_via_supported_long_method() -> None:
    class TelegraphClient(FakeTelegramClient):
        def __init__(self, config: PlatformConfig) -> None:
            super().__init__(config)
            self.telegraph_messages: list[dict] = []

        def send_telegraph(
            self,
            chat_id: int,
            content: str,
            reply_to_message_id: int | None = None,
        ) -> dict:
            self.telegraph_messages.append(
                {
                    "chat_id": chat_id,
                    "content": content,
                    "reply_to_message_id": reply_to_message_id,
                }
            )
            return {"message_id": 900}

    gateway = Gateway(
        GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
        lambda _: None,
        lambda _: None,
        _telegram_client_factory=TelegraphClient,
    )
    adapter = gateway._adapters_by_platform["telegram"]

    result = gateway.send(
        OutboundMessage(
            content="long",
            platform="telegram",
            format="telegraph",
            reply_to="8",
        )
    )

    assert result == DeliveryResult(
        success=True,
        platform="telegram",
        message_id="900",
    )
    assert adapter.client.telegraph_messages == [
        {"chat_id": 12345, "content": "long", "reply_to_message_id": 8}
    ]


def test_telegram_adapter_rejects_telegraph_without_long_content_method() -> None:
    gateway = Gateway(
        GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
        lambda _: None,
        lambda _: None,
        _telegram_client_factory=FakeTelegramClient,
    )
    adapter = gateway._adapters_by_platform["telegram"]

    result = gateway.send(
        OutboundMessage(content="long", platform="telegram", format="telegraph")
    )

    assert result == DeliveryResult(
        success=False,
        platform="telegram",
        message_id=None,
        error="telegram client does not expose a supported telegraph send method",
    )
    assert adapter.client.sent_messages == []
    assert adapter.client.api_requests == []


def test_telegram_adapter_converts_client_send_failure_to_delivery_result() -> None:
    class FailingClient(FakeTelegramClient):
        async def send_message(
            self,
            chat_id: int,
            text: str,
            reply_to: int | None = None,
        ) -> int:
            raise RuntimeError("telegram unavailable")

    gateway = Gateway(
        GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
        lambda _: None,
        lambda _: None,
        _telegram_client_factory=FailingClient,
    )

    result = gateway.send(OutboundMessage(content="plain", platform="telegram"))

    assert result == DeliveryResult(
        success=False,
        platform="telegram",
        message_id=None,
        error="telegram unavailable",
    )


def test_telegram_listener_polls_and_normalizes_inbound_messages() -> None:
    received = []
    gateway = Gateway(
        GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
        received.append,
        lambda _: None,
        _telegram_client_factory=PollingTelegramClient,
    )
    adapter = gateway._adapters_by_platform["telegram"]

    gateway.start_listener()
    _wait_for(lambda: len(received) == 1)
    gateway.stop_listener()

    assert received[0].content == "hello gateway"
    assert received[0].platform == "telegram"
    assert received[0].message_id == "77"
    assert received[0].sender == "human"
    assert received[0].timestamp == datetime.fromtimestamp(
        1_777_777_780, timezone.utc
    )
    assert received[0].reply_to == "55"
    assert received[0].raw["update_id"] == 10
    assert adapter.client.get_updates_calls[0] == {"offset": None, "timeout": 0}
    assert adapter.client.stopped is True


def test_telegram_listener_start_is_nonblocking_and_lifecycle_is_idempotent() -> None:
    gateway = Gateway(
        GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
        lambda _: None,
        lambda _: None,
        _telegram_client_factory=PollingTelegramClient,
    )
    adapter = gateway._adapters_by_platform["telegram"]

    gateway.start_listener()
    gateway.start_listener()
    _wait_for(lambda: len(adapter.client.get_updates_calls) >= 1)
    gateway.stop_listener()
    gateway.stop_listener()

    assert gateway._listening_platforms == set()
    assert adapter._listener_thread is None
    assert adapter.client.stopped is True


def test_telegram_listener_respects_listen_false() -> None:
    gateway = Gateway(
        GatewayConfig(
            platforms=[_telegram_platform()],
            default_platform="telegram",
            listen=False,
        ),
        lambda _: None,
        lambda _: None,
        _telegram_client_factory=PollingTelegramClient,
    )
    adapter = gateway._adapters_by_platform["telegram"]

    gateway.start_listener()

    assert adapter._listener_thread is None
    assert adapter.client.get_updates_calls == []


def test_mixed_log_and_telegram_delivery_tracks_platform_message_ids(tmp_path) -> None:
    log_path = tmp_path / "gateway.jsonl"
    gateway = Gateway(
        GatewayConfig(
            platforms=[
                _telegram_platform(),
                PlatformConfig(
                    name="log",
                    adapter_type="log",
                    credentials={},
                    params={"log_path": str(log_path)},
                ),
            ],
            default_platform="telegram",
        ),
        lambda _: None,
        lambda _: None,
        _telegram_client_factory=FakeTelegramClient,
    )
    telegram_adapter = gateway._adapters_by_platform["telegram"]

    telegram_result = gateway.send_to_default(
        "telegram thought",
        intent_tag="free_play",
    )
    log_result = gateway.send(
        OutboundMessage(
            content="local trace",
            platform="log",
            metadata={"source": "integration-test"},
        )
    )

    assert telegram_result == DeliveryResult(
        success=True,
        platform="telegram",
        message_id="201",
    )
    assert log_result == DeliveryResult(
        success=True,
        platform="log",
        message_id="log-1",
    )
    assert telegram_adapter.client.sent_messages == [
        {"chat_id": 12345, "text": "telegram thought", "reply_to": None}
    ]
    assert gateway._recent_deliveries[
        ("telegram", "201")
    ].intent_tag == "free_play"
    assert gateway._recent_deliveries[("log", "log-1")].metadata == {
        "source": "integration-test"
    }
    assert (
        json.loads(log_path.read_text(encoding="utf-8"))["content"]
        == "local trace"
    )


def test_mixed_log_and_telegram_listener_stop_cleans_up_all_platforms(tmp_path) -> None:
    log_path = tmp_path / "gateway.jsonl"
    gateway = Gateway(
        GatewayConfig(
            platforms=[
                _telegram_platform(),
                PlatformConfig(
                    name="log",
                    adapter_type="log",
                    credentials={},
                    params={"log_path": str(log_path)},
                ),
            ],
            default_platform="telegram",
        ),
        lambda _: None,
        lambda _: None,
        _telegram_client_factory=PollingTelegramClient,
    )
    telegram_adapter = gateway._adapters_by_platform["telegram"]

    gateway.start_listener()
    _wait_for(lambda: len(telegram_adapter.client.get_updates_calls) >= 1)
    assert gateway._listening_platforms == {"telegram", "log"}

    gateway.stop_listener()

    assert gateway._listening_platforms == set()
    assert telegram_adapter._listener_thread is None
    assert telegram_adapter.client.stopped is True
    assert not log_path.exists()


def test_telegram_callback_exceptions_remain_gateway_owned() -> None:
    received: list[str] = []

    def on_message(message) -> None:
        received.append(message.message_id)
        raise RuntimeError("callback failed")

    gateway = Gateway(
        GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
        on_message,
        lambda _: None,
        _telegram_client_factory=PollingTelegramClient,
    )

    gateway.start_listener()
    _wait_for(lambda: received == ["77"])
    gateway.stop_listener()

    assert [str(error) for error in gateway._callback_errors] == ["callback failed"]


def test_telegram_listener_normalizes_feedback_from_reactions_replies_and_edits() -> None:
    class FeedbackTelegramClient(PollingTelegramClient):
        def __init__(self, config: PlatformConfig) -> None:
            super().__init__(config)
            self.update_batches = [
                [
                    {
                        "update_id": 20,
                        "message_reaction": {
                            "message_id": 201,
                            "date": 1_777_777_781,
                            "user": {"id": 42, "username": "human"},
                            "new_reaction": [{"type": "emoji", "emoji": "heart"}],
                        },
                    },
                    {
                        "update_id": 21,
                        "message": {
                            "message_id": 202,
                            "date": 1_777_777_782,
                            "text": "that landed",
                            "from": {"id": 43},
                            "reply_to_message": {"message_id": 201},
                        },
                    },
                    {
                        "update_id": 22,
                        "edited_message": {
                            "message_id": 201,
                            "date": 1_777_777_780,
                            "edit_date": 1_777_777_783,
                            "text": "edited thought",
                            "from": {"id": 44, "username": "editor"},
                        },
                    },
                ]
            ]

    received: list[FeedbackSignal] = []
    gateway = Gateway(
        GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
        lambda _: None,
        received.append,
        _telegram_client_factory=FeedbackTelegramClient,
    )

    gateway.start_listener()
    _wait_for(lambda: len(received) == 3)
    gateway.stop_listener()

    normalized = [
        (signal.signal_type, signal.message_id, signal.value) for signal in received
    ]
    assert normalized == [
        ("reaction", "201", "heart"),
        ("reply", "201", "that landed"),
        ("edit", "201", "edited thought"),
    ]
    assert [signal.sender for signal in received] == ["human", "43", "editor"]
    assert received[0].timestamp == datetime.fromtimestamp(
        1_777_777_781, timezone.utc
    )
    assert received[2].timestamp == datetime.fromtimestamp(
        1_777_777_783, timezone.utc
    )
    assert received[0].raw["update_id"] == 20
    assert received[1].raw["message"]["message_id"] == 202


def test_telegram_feedback_callback_exceptions_remain_gateway_owned() -> None:
    class FeedbackTelegramClient(PollingTelegramClient):
        def __init__(self, config: PlatformConfig) -> None:
            super().__init__(config)
            self.update_batches = [
                [
                    {
                        "update_id": 23,
                        "message_reaction": {
                            "message_id": 300,
                            "date": 1_777_777_784,
                            "user": {"id": 42},
                            "new_reaction": [{"type": "emoji", "emoji": "thumbs_up"}],
                        },
                    }
                ]
            ]

    received: list[str] = []

    def on_feedback(signal: FeedbackSignal) -> None:
        received.append(signal.message_id)
        raise RuntimeError("feedback failed")

    gateway = Gateway(
        GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
        lambda _: None,
        on_feedback,
        _telegram_client_factory=FeedbackTelegramClient,
    )

    gateway.start_listener()
    _wait_for(lambda: received == ["300"])
    gateway.stop_listener()

    assert [str(error) for error in gateway._callback_errors] == ["feedback failed"]


def test_telegram_adapter_rejects_noncallable_client_factory() -> None:
    with pytest.raises(PlatformConfigError, match="failed to create adapter"):
        Gateway(
            GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
            lambda _: None,
            lambda _: None,
            _telegram_client_factory=object(),
        )


def test_telegram_adapter_wraps_client_factory_failure() -> None:
    def factory(config: PlatformConfig) -> FakeTelegramClient:
        raise RuntimeError("factory failed")

    with pytest.raises(PlatformConfigError, match="failed to create adapter"):
        Gateway(
            GatewayConfig(platforms=[_telegram_platform()], default_platform="telegram"),
            lambda _: None,
            lambda _: None,
            _telegram_client_factory=factory,
        )
