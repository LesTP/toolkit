"""Gateway manager entry point."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping

from toolkit.gateway.adapters import (
    DEFAULT_ADAPTER_REGISTRY,
    AdapterFactory,
    AdapterRegistry,
    GatewayAdapter,
    TelegramClientFactory,
    telegram_adapter_factory,
)
from toolkit.gateway.errors import (
    DeliveryError,
    FormatNotSupportedError,
    PlatformConfigError,
    PlatformConnectionError,
    PlatformNotFoundError,
)
from toolkit.gateway.types import (
    DeliveryResult,
    FeedbackSignal,
    GatewayConfig,
    InboundMessage,
    OutboundMessage,
    PlatformConfig,
)


_SUPPORTED_ADAPTER_TYPES = {"telegram", "log", "fake"}
_SUPPORTED_OUTPUT_FORMATS = {"text", "markdown", "thread", "telegraph"}

_REQUIRED_CREDENTIAL_KEYS = {
    "telegram": (("bot_token",),),
}
_REQUIRED_PARAM_KEYS = {
    "telegram": (("chat_id",),),
    "log": (("log_path",),),
}
_RECENT_MESSAGE_LIMIT = 100


class Gateway:
    """Gateway public entry point."""

    def __init__(
        self,
        config: GatewayConfig,
        on_message: Callable[[InboundMessage], None],
        on_feedback: Callable[[FeedbackSignal], None],
        *,
        _adapter_factories: Mapping[str, AdapterFactory] | None = None,
        _telegram_client_factory: TelegramClientFactory | None = None,
    ) -> None:
        self.config = config
        self.on_message = on_message
        self.on_feedback = on_feedback
        adapter_factories = dict(_adapter_factories or {})
        if _telegram_client_factory is not None:
            adapter_factories["telegram"] = lambda platform: telegram_adapter_factory(
                platform,
                client_factory=_telegram_client_factory,
            )
        try:
            self._adapter_registry = DEFAULT_ADAPTER_REGISTRY.with_factories(
                adapter_factories
            )
        except (TypeError, ValueError) as exc:
            raise PlatformConfigError(f"invalid adapter registry: {exc}") from exc
        self._platforms_by_name = _validate_and_index_platforms(
            config, self._adapter_registry
        )
        self._adapters_by_platform = self._build_enabled_adapters()
        self._listening_platforms: set[str] = set()
        self._recent_deliveries: OrderedDict[
            tuple[str, str], OutboundMessage
        ] = OrderedDict()
        self._callback_errors: list[Exception] = []

    def send(self, message: OutboundMessage) -> DeliveryResult:
        platform = self._get_enabled_platform(message.platform)
        _validate_message_format(message, platform)
        adapter = self._adapters_by_platform[platform.name]
        try:
            result = adapter.send(message)
        except DeliveryError as exc:
            return DeliveryResult(
                success=False,
                platform=platform.name,
                message_id=None,
                error=str(exc),
            )
        except Exception as exc:
            return DeliveryResult(
                success=False,
                platform=platform.name,
                message_id=None,
                error=str(exc),
            )
        self._remember_delivery(result, message)
        return result

    def send_to_default(
        self,
        content: str,
        format: str = "text",
        intent_tag: str | None = None,
    ) -> DeliveryResult:
        return self.send(
            OutboundMessage(
                content=content,
                platform=self.config.default_platform,
                format=format,
                intent_tag=intent_tag,
            )
        )

    def start_listener(self) -> None:
        if not self.config.listen:
            return

        for platform_name, adapter in self._adapters_by_platform.items():
            if platform_name in self._listening_platforms:
                continue
            try:
                self._listening_platforms.add(platform_name)
                adapter.start_listener(
                    self._message_dispatcher(platform_name),
                    self._feedback_dispatcher(platform_name),
                )
            except PlatformConnectionError:
                self._listening_platforms.discard(platform_name)
                raise
            except Exception as exc:
                self._listening_platforms.discard(platform_name)
                raise PlatformConnectionError(
                    f"failed to start listener for platform {platform_name}: {exc}"
                ) from exc

    def stop_listener(self) -> None:
        for platform_name in list(self._listening_platforms):
            adapter = self._adapters_by_platform[platform_name]
            adapter.stop_listener()
            self._listening_platforms.remove(platform_name)

    def _enabled_platform_configs(self) -> list[PlatformConfig]:
        return [platform for platform in self.config.platforms if platform.enabled]

    def _build_enabled_adapters(self) -> dict[str, GatewayAdapter]:
        adapters: dict[str, GatewayAdapter] = {}
        for platform in self._enabled_platform_configs():
            try:
                adapters[platform.name] = self._adapter_registry.create(platform)
            except Exception as exc:
                raise PlatformConfigError(
                    f"failed to create adapter for platform {platform.name}: {exc}"
                ) from exc
        return adapters

    def _get_enabled_platform(self, platform_name: str) -> PlatformConfig:
        try:
            platform = self._platforms_by_name[platform_name]
        except KeyError as exc:
            raise PlatformNotFoundError(
                f"platform not found: {platform_name}"
            ) from exc
        if not platform.enabled:
            raise PlatformNotFoundError(f"platform is disabled: {platform_name}")
        return platform

    def _message_dispatcher(
        self, platform_name: str
    ) -> Callable[[InboundMessage], None]:
        def dispatch(message: InboundMessage) -> None:
            if platform_name not in self._listening_platforms:
                return
            try:
                self.on_message(message)
            except Exception as exc:
                # Callback failures are isolated so adapter listener loops keep running.
                self._callback_errors.append(exc)

        return dispatch

    def _feedback_dispatcher(
        self, platform_name: str
    ) -> Callable[[FeedbackSignal], None]:
        def dispatch(signal: FeedbackSignal) -> None:
            if platform_name not in self._listening_platforms:
                return
            try:
                self.on_feedback(signal)
            except Exception as exc:
                # Callback failures are isolated so adapter listener loops keep running.
                self._callback_errors.append(exc)

        return dispatch

    def _remember_delivery(
        self,
        result: DeliveryResult,
        message: OutboundMessage,
    ) -> None:
        if not result.success or result.message_id is None:
            return

        key = (result.platform, result.message_id)
        self._recent_deliveries[key] = message
        self._recent_deliveries.move_to_end(key)
        while len(self._recent_deliveries) > _RECENT_MESSAGE_LIMIT:
            self._recent_deliveries.popitem(last=False)


def _validate_and_index_platforms(
    config: GatewayConfig,
    adapter_registry: AdapterRegistry | None = None,
) -> dict[str, PlatformConfig]:
    registry = adapter_registry or DEFAULT_ADAPTER_REGISTRY
    platforms_by_name: dict[str, PlatformConfig] = {}
    for platform in config.platforms:
        _validate_platform_config(platform, registry)
        if platform.name in platforms_by_name:
            raise PlatformConfigError(f"duplicate platform name: {platform.name}")
        platforms_by_name[platform.name] = platform

    default_platform = platforms_by_name.get(config.default_platform)
    if default_platform is None:
        raise PlatformConfigError(
            f"default platform not configured: {config.default_platform}"
        )
    if not default_platform.enabled:
        raise PlatformConfigError(
            f"default platform is disabled: {config.default_platform}"
        )

    return platforms_by_name


def _validate_platform_config(
    platform: PlatformConfig,
    adapter_registry: AdapterRegistry | None = None,
) -> None:
    registry = adapter_registry or DEFAULT_ADAPTER_REGISTRY
    if not platform.name:
        raise PlatformConfigError("platform name is required")
    if not platform.adapter_type:
        raise PlatformConfigError("platform adapter_type is required")
    if platform.adapter_type not in _SUPPORTED_ADAPTER_TYPES or not registry.supports(
        platform.adapter_type
    ):
        raise PlatformConfigError(f"unknown adapter_type: {platform.adapter_type}")

    _validate_required_keys(
        platform.params,
        _REQUIRED_PARAM_KEYS.get(platform.adapter_type, ()),
        "params",
        platform.adapter_type,
    )
    _validate_required_keys(
        platform.credentials,
        _REQUIRED_CREDENTIAL_KEYS.get(platform.adapter_type, ()),
        "credentials",
        platform.adapter_type,
    )
    _validate_output_formats(platform)


def _validate_required_keys(
    values: dict | None,
    acceptable_key_sets: tuple[tuple[str, ...], ...],
    field_name: str,
    adapter_type: str,
) -> None:
    if not acceptable_key_sets:
        return

    value_map = values or {}
    for key_set in acceptable_key_sets:
        if all(_has_value(value_map, key) for key in key_set):
            return

    required = " or ".join(", ".join(key_set) for key_set in acceptable_key_sets)
    raise PlatformConfigError(
        f"{adapter_type} adapter missing required {field_name}: {required}"
    )


def _has_value(values: dict, key: str) -> bool:
    value = values.get(key)
    return value is not None and value != ""


def _validate_output_formats(platform: PlatformConfig) -> None:
    if not platform.output_formats:
        raise PlatformConfigError(
            f"platform output_formats must not be empty: {platform.name}"
        )
    unsupported = [
        output_format
        for output_format in platform.output_formats
        if output_format not in _SUPPORTED_OUTPUT_FORMATS
    ]
    if unsupported:
        raise PlatformConfigError(
            f"platform output_formats contain unsupported formats: {', '.join(unsupported)}"
        )


def _validate_message_format(
    message: OutboundMessage,
    platform: PlatformConfig,
) -> None:
    if message.format not in platform.output_formats:
        raise FormatNotSupportedError(
            f"format not supported by platform {platform.name}: {message.format}"
        )
