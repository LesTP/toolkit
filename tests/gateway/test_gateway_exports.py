from dataclasses import fields
from datetime import datetime

import toolkit.gateway as gateway
from toolkit.gateway import (
    DeliveryError,
    DeliveryResult,
    FeedbackSignal,
    FormatNotSupportedError,
    Gateway,
    GatewayConfig,
    GatewayError,
    InboundMessage,
    OutboundMessage,
    PlatformConfig,
    PlatformConfigError,
    PlatformConnectionError,
    PlatformNotFoundError,
)


def test_package_exports_arch_public_api() -> None:
    expected_exports = {
        "DeliveryError",
        "DeliveryResult",
        "FeedbackSignal",
        "FormatNotSupportedError",
        "Gateway",
        "GatewayConfig",
        "GatewayError",
        "InboundMessage",
        "OutboundMessage",
        "PlatformConfig",
        "PlatformConfigError",
        "PlatformConnectionError",
        "PlatformNotFoundError",
    }

    assert set(gateway.__all__) == expected_exports
    for exported_name in expected_exports:
        assert getattr(gateway, exported_name) is not None


def test_arch_dataclass_field_names_match_contract() -> None:
    assert [field.name for field in fields(GatewayConfig)] == [
        "platforms",
        "default_platform",
        "listen",
    ]
    assert [field.name for field in fields(PlatformConfig)] == [
        "name",
        "adapter_type",
        "credentials",
        "params",
        "enabled",
        "output_formats",
    ]
    assert [field.name for field in fields(InboundMessage)] == [
        "content",
        "platform",
        "message_id",
        "sender",
        "timestamp",
        "reply_to",
        "reactions",
        "raw",
    ]
    assert [field.name for field in fields(OutboundMessage)] == [
        "content",
        "platform",
        "format",
        "reply_to",
        "intent_tag",
        "metadata",
    ]
    assert [field.name for field in fields(DeliveryResult)] == [
        "success",
        "platform",
        "message_id",
        "error",
    ]
    assert [field.name for field in fields(FeedbackSignal)] == [
        "platform",
        "message_id",
        "signal_type",
        "value",
        "sender",
        "timestamp",
    ]


def test_arch_dataclasses_construct_with_expected_defaults() -> None:
    timestamp = datetime(2026, 1, 1)
    platform = PlatformConfig(name="log", adapter_type="log", credentials={})
    valid_platform = PlatformConfig(
        name="log",
        adapter_type="log",
        credentials={},
        params={"log_path": "/tmp/phosphene.log"},
    )
    config = GatewayConfig(platforms=[valid_platform], default_platform="log")
    inbound = InboundMessage(
        content="hello",
        platform="log",
        message_id="in-1",
        sender="human",
        timestamp=timestamp,
    )
    outbound = OutboundMessage(content="reply", platform="log")
    result = DeliveryResult(success=True, platform="log", message_id="out-1")
    feedback = FeedbackSignal(
        platform="log",
        message_id="out-1",
        signal_type="reaction",
        sender="human",
        timestamp=timestamp,
    )

    assert config.listen is True
    assert platform.params == {}
    assert platform.enabled is True
    assert platform.output_formats == ["text"]
    assert inbound.reply_to is None
    assert inbound.reactions is None
    assert inbound.raw is None
    assert outbound.format == "text"
    assert outbound.reply_to is None
    assert outbound.intent_tag is None
    assert outbound.metadata == {}
    assert result.error is None
    assert feedback.value is None
    assert issubclass(PlatformConfigError, GatewayError)
    assert issubclass(PlatformConnectionError, GatewayError)
    assert issubclass(PlatformNotFoundError, GatewayError)
    assert issubclass(FormatNotSupportedError, GatewayError)
    assert issubclass(DeliveryError, GatewayError)
    assert isinstance(Gateway(config, lambda _: None, lambda _: None), Gateway)
