import pytest

from toolkit.gateway import (
    DeliveryError,
    DeliveryResult,
    FormatNotSupportedError,
    Gateway,
    GatewayConfig,
    OutboundMessage,
    PlatformConfig,
    PlatformNotFoundError,
)


class RecordingAdapter:
    def __init__(
        self,
        config: PlatformConfig,
        *,
        result: DeliveryResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.config = config
        self.result = result
        self.error = error
        self.sent: list[OutboundMessage] = []

    def send(self, message: OutboundMessage) -> DeliveryResult:
        self.sent.append(message)
        if self.error is not None:
            raise self.error
        return self.result or DeliveryResult(
            success=True,
            platform=self.config.name,
            message_id="sent-1",
        )

    def start_listener(self, on_message, on_feedback) -> None:
        return None

    def stop_listener(self) -> None:
        return None


def _platform(name: str = "fake", formats: list[str] | None = None) -> PlatformConfig:
    return PlatformConfig(
        name=name,
        adapter_type="fake",
        credentials={},
        output_formats=formats or ["text"],
    )


def _gateway(
    *platforms: PlatformConfig,
    default: str | None = None,
    factory,
) -> Gateway:
    return Gateway(
        GatewayConfig(
            platforms=list(platforms),
            default_platform=default or platforms[0].name,
        ),
        lambda _: None,
        lambda _: None,
        _adapter_factories={"fake": factory},
    )


def test_send_routes_to_target_platform_and_preserves_message_fields() -> None:
    adapters: dict[str, RecordingAdapter] = {}

    def factory(config: PlatformConfig) -> RecordingAdapter:
        adapter = RecordingAdapter(
            config,
            result=DeliveryResult(
                success=True,
                platform=config.name,
                message_id=f"{config.name}-42",
            ),
        )
        adapters[config.name] = adapter
        return adapter

    gateway = _gateway(
        _platform("primary"),
        _platform("secondary", ["text", "markdown", "thread"]),
        factory=factory,
    )
    message = OutboundMessage(
        content="reply",
        platform="secondary",
        format="thread",
        reply_to="in-1",
        intent_tag="synthesis",
        metadata={"parse_mode": "MarkdownV2"},
    )

    result = gateway.send(message)

    assert result == DeliveryResult(
        success=True,
        platform="secondary",
        message_id="secondary-42",
    )
    assert adapters["primary"].sent == []
    assert adapters["secondary"].sent == [message]
    assert adapters["secondary"].sent[0].reply_to == "in-1"
    assert adapters["secondary"].sent[0].intent_tag == "synthesis"
    assert adapters["secondary"].sent[0].metadata == {"parse_mode": "MarkdownV2"}


def test_send_rejects_unknown_or_disabled_platform_before_adapter_call() -> None:
    adapters: list[RecordingAdapter] = []

    def factory(config: PlatformConfig) -> RecordingAdapter:
        adapter = RecordingAdapter(config)
        adapters.append(adapter)
        return adapter

    gateway = _gateway(
        _platform("enabled"),
        PlatformConfig(
            name="disabled",
            adapter_type="fake",
            credentials={},
            enabled=False,
        ),
        factory=factory,
    )

    with pytest.raises(PlatformNotFoundError, match="platform not found"):
        gateway.send(OutboundMessage(content="missing", platform="missing"))
    with pytest.raises(PlatformNotFoundError, match="platform is disabled"):
        gateway.send(OutboundMessage(content="disabled", platform="disabled"))

    assert adapters[0].sent == []


def test_send_rejects_unsupported_format_before_adapter_call() -> None:
    adapters: list[RecordingAdapter] = []

    def factory(config: PlatformConfig) -> RecordingAdapter:
        adapter = RecordingAdapter(config)
        adapters.append(adapter)
        return adapter

    gateway = _gateway(_platform("fake", ["text"]), factory=factory)

    with pytest.raises(FormatNotSupportedError, match="format not supported"):
        gateway.send(
            OutboundMessage(content="rich", platform="fake", format="markdown")
        )

    assert adapters[0].sent == []


def test_send_converts_adapter_delivery_error_to_failure_result() -> None:
    def factory(config: PlatformConfig) -> RecordingAdapter:
        return RecordingAdapter(config, error=DeliveryError("rate limited"))

    gateway = _gateway(_platform("fake"), factory=factory)

    result = gateway.send(OutboundMessage(content="hello", platform="fake"))

    assert result == DeliveryResult(
        success=False,
        platform="fake",
        message_id=None,
        error="rate limited",
    )


def test_send_to_default_uses_default_platform_and_intent_tag() -> None:
    adapters: dict[str, RecordingAdapter] = {}

    def factory(config: PlatformConfig) -> RecordingAdapter:
        adapter = RecordingAdapter(config)
        adapters[config.name] = adapter
        return adapter

    gateway = _gateway(
        _platform("primary"),
        _platform("default"),
        default="default",
        factory=factory,
    )

    result = gateway.send_to_default(
        "free play",
        format="text",
        intent_tag="free_play",
    )

    assert result == DeliveryResult(
        success=True,
        platform="default",
        message_id="sent-1",
    )
    assert adapters["primary"].sent == []
    assert adapters["default"].sent == [
        OutboundMessage(
            content="free play",
            platform="default",
            format="text",
            intent_tag="free_play",
        )
    ]
