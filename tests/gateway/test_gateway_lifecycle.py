import pytest

from toolkit.gateway import (
    Gateway,
    GatewayConfig,
    PlatformConfig,
    PlatformConfigError,
    PlatformConnectionError,
)


class TrackingAdapter:
    def __init__(self, config: PlatformConfig) -> None:
        self.config = config
        self.starts = 0
        self.stops = 0

    def start_listener(self, on_message, on_feedback) -> None:
        self.starts += 1

    def stop_listener(self) -> None:
        self.stops += 1


class FailingAdapter:
    def __init__(self, config: PlatformConfig) -> None:
        self.config = config

    def start_listener(self, on_message, on_feedback) -> None:
        raise RuntimeError("connection refused")

    def stop_listener(self) -> None:
        return None


def _fake_platform(name: str = "fake") -> PlatformConfig:
    return PlatformConfig(name=name, adapter_type="fake", credentials={})


def _gateway(
    *platforms: PlatformConfig,
    listen: bool = True,
    factories=None,
) -> Gateway:
    return Gateway(
        GatewayConfig(
            platforms=list(platforms),
            default_platform=platforms[0].name,
            listen=listen,
        ),
        lambda _: None,
        lambda _: None,
        _adapter_factories=factories,
    )


def test_gateway_constructs_enabled_fake_adapters_only() -> None:
    gateway = _gateway(
        _fake_platform("primary"),
        PlatformConfig(
            name="disabled",
            adapter_type="fake",
            credentials={},
            enabled=False,
        ),
    )

    assert list(gateway._adapters_by_platform) == ["primary"]


def test_gateway_rejects_invalid_factory_snapshot() -> None:
    with pytest.raises(PlatformConfigError, match="invalid adapter registry"):
        _gateway(_fake_platform(), factories={"fake": object()})


def test_gateway_start_stop_listener_are_idempotent() -> None:
    adapters: list[TrackingAdapter] = []

    def factory(config: PlatformConfig) -> TrackingAdapter:
        adapter = TrackingAdapter(config)
        adapters.append(adapter)
        return adapter

    gateway = _gateway(_fake_platform(), factories={"fake": factory})

    gateway.start_listener()
    gateway.start_listener()
    gateway.stop_listener()
    gateway.stop_listener()

    assert adapters[0].starts == 1
    assert adapters[0].stops == 1
    assert gateway._listening_platforms == set()


def test_gateway_start_listener_respects_listen_false() -> None:
    adapters: list[TrackingAdapter] = []

    def factory(config: PlatformConfig) -> TrackingAdapter:
        adapter = TrackingAdapter(config)
        adapters.append(adapter)
        return adapter

    gateway = _gateway(_fake_platform(), listen=False, factories={"fake": factory})

    gateway.start_listener()

    assert adapters[0].starts == 0
    assert gateway._listening_platforms == set()


def test_gateway_wraps_platform_connection_errors() -> None:
    gateway = _gateway(_fake_platform(), factories={"fake": FailingAdapter})

    with pytest.raises(PlatformConnectionError, match="failed to start listener"):
        gateway.start_listener()

    assert gateway._listening_platforms == set()
