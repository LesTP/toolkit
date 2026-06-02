import pytest

from toolkit.gateway import (
    Gateway,
    GatewayConfig,
    PlatformConfig,
    PlatformConfigError,
    PlatformNotFoundError,
)


def _gateway_config(*platforms: PlatformConfig, default: str = "log") -> GatewayConfig:
    return GatewayConfig(platforms=list(platforms), default_platform=default)


class FakeTelegramClient:
    def __init__(self, config: PlatformConfig) -> None:
        self.config = config


def _telegram_client_factory(config: PlatformConfig) -> FakeTelegramClient:
    return FakeTelegramClient(config)


def _gateway(config: GatewayConfig) -> Gateway:
    return Gateway(
        config,
        lambda _: None,
        lambda _: None,
        _telegram_client_factory=_telegram_client_factory,
    )


def test_gateway_accepts_valid_arch_platform_configs() -> None:
    gateway = _gateway(
        _gateway_config(
            PlatformConfig(
                name="telegram",
                adapter_type="telegram",
                credentials={"bot_token": "token"},
                params={"chat_id": "12345"},
                output_formats=["text", "markdown", "telegraph", "thread"],
            ),
            PlatformConfig(
                name="log",
                adapter_type="log",
                credentials={},
                params={"log_path": "/tmp/phosphene.log"},
            ),
            default="telegram",
        )
    )

    assert [platform.name for platform in gateway._enabled_platform_configs()] == [
        "telegram",
        "log",
    ]


def test_gateway_rejects_duplicate_platform_names() -> None:
    with pytest.raises(PlatformConfigError, match="duplicate platform name"):
        _gateway(
            _gateway_config(
                PlatformConfig(
                    name="same",
                    adapter_type="log",
                    credentials={},
                    params={"log_path": "/tmp/a.log"},
                ),
                PlatformConfig(
                    name="same",
                    adapter_type="log",
                    credentials={},
                    params={"log_path": "/tmp/b.log"},
                ),
                default="same",
            )
        )


def test_gateway_rejects_missing_default_platform() -> None:
    with pytest.raises(PlatformConfigError, match="default platform not configured"):
        _gateway(
            _gateway_config(
                PlatformConfig(
                    name="log",
                    adapter_type="log",
                    credentials={},
                    params={"log_path": "/tmp/phosphene.log"},
                ),
                default="telegram",
            )
        )


def test_gateway_rejects_disabled_default_platform() -> None:
    with pytest.raises(PlatformConfigError, match="default platform is disabled"):
        _gateway(
            _gateway_config(
                PlatformConfig(
                    name="log",
                    adapter_type="log",
                    credentials={},
                    params={"log_path": "/tmp/phosphene.log"},
                    enabled=False,
                )
            )
        )


def test_gateway_rejects_unknown_adapter_type() -> None:
    with pytest.raises(PlatformConfigError, match="unknown adapter_type"):
        _gateway(
            _gateway_config(
                PlatformConfig(
                    name="webhook",
                    adapter_type="webhook",
                    credentials={},
                ),
                default="webhook",
            )
        )


@pytest.mark.parametrize(
    ("platform", "message"),
    [
        (
            PlatformConfig(name="", adapter_type="log", credentials={}),
            "platform name is required",
        ),
        (
            PlatformConfig(name="log", adapter_type="", credentials={}),
            "platform adapter_type is required",
        ),
        (
            PlatformConfig(
                name="telegram",
                adapter_type="telegram",
                credentials={},
                params={"chat_id": "12345"},
            ),
            "telegram adapter missing required credentials",
        ),
        (
            PlatformConfig(
                name="telegram",
                adapter_type="telegram",
                credentials={"bot_token": "token"},
            ),
            "telegram adapter missing required params",
        ),
        (
            PlatformConfig(name="log", adapter_type="log", credentials={}),
            "log adapter missing required params",
        ),
    ],
)
def test_gateway_rejects_missing_required_fields(
    platform: PlatformConfig, message: str
) -> None:
    with pytest.raises(PlatformConfigError, match=message):
        _gateway(_gateway_config(platform, default=platform.name))


def test_gateway_rejects_empty_output_formats() -> None:
    with pytest.raises(PlatformConfigError, match="output_formats must not be empty"):
        _gateway(
            _gateway_config(
                PlatformConfig(
                    name="log",
                    adapter_type="log",
                    credentials={},
                    params={"log_path": "/tmp/phosphene.log"},
                    output_formats=[],
                )
            )
        )


def test_gateway_rejects_unknown_output_formats() -> None:
    with pytest.raises(
        PlatformConfigError, match="output_formats contain unsupported formats"
    ):
        _gateway(
            _gateway_config(
                PlatformConfig(
                    name="log",
                    adapter_type="log",
                    credentials={},
                    params={"log_path": "/tmp/phosphene.log"},
                    output_formats=["text", "html"],
                )
            )
        )


def test_gateway_filters_disabled_non_default_platforms() -> None:
    gateway = _gateway(
        _gateway_config(
            PlatformConfig(
                name="log",
                adapter_type="log",
                credentials={},
                params={"log_path": "/tmp/phosphene.log"},
            ),
            PlatformConfig(
                name="telegram",
                adapter_type="telegram",
                credentials={"bot_token": "token"},
                params={"chat_id": "12345"},
                enabled=False,
            ),
        )
    )

    assert [platform.name for platform in gateway._enabled_platform_configs()] == ["log"]
    with pytest.raises(PlatformNotFoundError, match="platform is disabled"):
        gateway._get_enabled_platform("telegram")
