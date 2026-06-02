from datetime import datetime

from toolkit.gateway import (
    FeedbackSignal,
    Gateway,
    GatewayConfig,
    InboundMessage,
    OutboundMessage,
    PlatformConfig,
)


def _gateway(on_message, on_feedback) -> Gateway:
    return Gateway(
        GatewayConfig(
            platforms=[
                PlatformConfig(
                    name="fake",
                    adapter_type="fake",
                    credentials={},
                )
            ],
            default_platform="fake",
        ),
        on_message,
        on_feedback,
    )


def test_fake_adapter_dispatches_inbound_callbacks_with_metadata() -> None:
    received: list[InboundMessage] = []
    gateway = _gateway(received.append, lambda _: None)
    adapter = gateway._adapters_by_platform["fake"]
    timestamp = datetime(2026, 1, 1, 12, 0)
    message = InboundMessage(
        content="hello",
        platform="fake",
        message_id="in-1",
        sender="human",
        timestamp=timestamp,
        reply_to="out-1",
        reactions=["thumbs-up"],
        raw={"update_id": 12},
    )

    gateway.start_listener()
    adapter.dispatch_inbound(message)

    assert received == [message]
    assert received[0].message_id == "in-1"
    assert received[0].raw == {"update_id": 12}


def test_fake_adapter_dispatches_feedback_callbacks_with_metadata() -> None:
    received: list[FeedbackSignal] = []
    gateway = _gateway(lambda _: None, received.append)
    adapter = gateway._adapters_by_platform["fake"]
    signal = FeedbackSignal(
        platform="fake",
        message_id="out-1",
        signal_type="reaction",
        value="heart",
        sender="human",
        timestamp=datetime(2026, 1, 1, 12, 0),
    )

    gateway.start_listener()
    adapter.dispatch_feedback(signal)

    assert received == [signal]
    assert received[0].message_id == "out-1"
    assert received[0].value == "heart"


def test_callback_exceptions_are_isolated_and_recorded() -> None:
    received: list[str] = []

    def on_message(message: InboundMessage) -> None:
        received.append(message.message_id)
        raise RuntimeError(f"bad callback: {message.message_id}")

    gateway = _gateway(on_message, lambda _: None)
    adapter = gateway._adapters_by_platform["fake"]
    gateway.start_listener()

    adapter.dispatch_inbound(
        InboundMessage(
            content="first",
            platform="fake",
            message_id="in-1",
            sender="human",
            timestamp=datetime(2026, 1, 1, 12, 0),
        )
    )
    adapter.dispatch_inbound(
        InboundMessage(
            content="second",
            platform="fake",
            message_id="in-2",
            sender="human",
            timestamp=datetime(2026, 1, 1, 12, 1),
        )
    )

    assert received == ["in-1", "in-2"]
    assert [str(error) for error in gateway._callback_errors] == [
        "bad callback: in-1",
        "bad callback: in-2",
    ]


def test_stop_listener_prevents_later_fake_dispatch() -> None:
    received: list[InboundMessage] = []
    gateway = _gateway(received.append, lambda _: None)
    adapter = gateway._adapters_by_platform["fake"]

    gateway.start_listener()
    gateway.stop_listener()
    adapter.dispatch_inbound(
        InboundMessage(
            content="late",
            platform="fake",
            message_id="in-1",
            sender="human",
            timestamp=datetime(2026, 1, 1, 12, 0),
        )
    )

    assert received == []


def test_successful_delivery_records_bounded_recent_message_mapping() -> None:
    gateway = _gateway(lambda _: None, lambda _: None)

    for index in range(101):
        gateway.send(OutboundMessage(content=str(index), platform="fake"))

    assert ("fake", "fake-1") not in gateway._recent_deliveries
    assert gateway._recent_deliveries[("fake", "fake-101")] == OutboundMessage(
        content="100",
        platform="fake",
    )
    assert len(gateway._recent_deliveries) == 100
