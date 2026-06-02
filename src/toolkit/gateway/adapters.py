"""Internal adapter protocol and registry for Gateway."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import inspect
import json
from pathlib import Path
import threading
from typing import Protocol

from toolkit.gateway.errors import PlatformConfigError, PlatformConnectionError
from toolkit.gateway.types import (
    DeliveryResult,
    FeedbackSignal,
    InboundMessage,
    OutboundMessage,
    PlatformConfig,
)

InboundCallback = Callable[[InboundMessage], None]
FeedbackCallback = Callable[[FeedbackSignal], None]


class GatewayAdapter(Protocol):
    """Internal interface implemented by concrete Gateway adapters."""

    def send(self, message: OutboundMessage) -> DeliveryResult:
        """Deliver an outbound message through this adapter."""

    def start_listener(
        self,
        on_message: InboundCallback,
        on_feedback: FeedbackCallback,
    ) -> None:
        """Start adapter-owned inbound listening if supported."""

    def stop_listener(self) -> None:
        """Stop adapter-owned inbound listening if supported."""


AdapterFactory = Callable[[PlatformConfig], GatewayAdapter]
TelegramClientFactory = Callable[[PlatformConfig], object]


class AdapterRegistry:
    """Immutable internal Gateway adapter factory registry."""

    def __init__(self, factories: Mapping[str, AdapterFactory]) -> None:
        self._factories = dict(factories)
        for adapter_type, factory in self._factories.items():
            if not adapter_type:
                raise ValueError("adapter_type is required")
            if not callable(factory):
                raise TypeError(f"adapter factory for {adapter_type} must be callable")

    def with_factories(
        self, factories: Mapping[str, AdapterFactory] | None
    ) -> "AdapterRegistry":
        if not factories:
            return self
        merged = dict(self._factories)
        merged.update(factories)
        return AdapterRegistry(merged)

    def supports(self, adapter_type: str) -> bool:
        return adapter_type in self._factories

    def create(self, config: PlatformConfig) -> GatewayAdapter:
        return self._factories[config.adapter_type](config)


class OutputOnlyAdapter:
    """Adapter base for platforms with no inbound listener in this phase."""

    def __init__(self, config: PlatformConfig) -> None:
        self.config = config
        self.listener_started = False
        self.sent_messages: list[OutboundMessage] = []
        self._on_message: InboundCallback | None = None
        self._on_feedback: FeedbackCallback | None = None

    def send(self, message: OutboundMessage) -> DeliveryResult:
        self.sent_messages.append(message)
        return DeliveryResult(
            success=True,
            platform=self.config.name,
            message_id=f"{self.config.name}-{len(self.sent_messages)}",
        )

    def start_listener(
        self,
        on_message: InboundCallback,
        on_feedback: FeedbackCallback,
    ) -> None:
        self.listener_started = True
        self._on_message = on_message
        self._on_feedback = on_feedback

    def stop_listener(self) -> None:
        self.listener_started = False
        self._on_message = None
        self._on_feedback = None


class FakeGatewayAdapter(OutputOnlyAdapter):
    """Deterministic in-process adapter for Gateway lifecycle tests."""

    def dispatch_inbound(self, message: InboundMessage) -> None:
        if self.listener_started and self._on_message is not None:
            self._on_message(message)

    def dispatch_feedback(self, signal: FeedbackSignal) -> None:
        if self.listener_started and self._on_feedback is not None:
            self._on_feedback(signal)


class LogGatewayAdapter:
    """Local development adapter that appends outbound messages as JSON lines."""

    def __init__(self, config: PlatformConfig) -> None:
        self.config = config
        self.log_path = Path(config.params["log_path"])
        self.sent_count = 0

    def send(self, message: OutboundMessage) -> DeliveryResult:
        self.sent_count += 1
        message_id = f"{self.config.name}-{self.sent_count}"
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "platform": self.config.name,
            "message_id": message_id,
            "content": message.content,
            "format": message.format,
            "reply_to": message.reply_to,
            "intent_tag": message.intent_tag,
            "metadata": message.metadata,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record, sort_keys=True) + "\n")

        return DeliveryResult(
            success=True,
            platform=self.config.name,
            message_id=message_id,
        )

    def start_listener(
        self,
        on_message: InboundCallback,
        on_feedback: FeedbackCallback,
    ) -> None:
        return None

    def stop_listener(self) -> None:
        return None


class TelegramGatewayAdapter:
    """Telegram Gateway adapter backed by toolkit/telegram_client."""

    def __init__(
        self,
        config: PlatformConfig,
        client_factory: TelegramClientFactory | None = None,
    ) -> None:
        self.config = config
        self.chat_id = config.params["chat_id"]
        factory = client_factory or default_telegram_client_factory
        if not callable(factory):
            raise PlatformConfigError("telegram client factory must be callable")
        self.client = factory(config)
        self._poll_interval_seconds = float(
            config.params.get("poll_interval_seconds", 0.1)
        )
        self._poll_timeout_seconds = int(config.params.get("poll_timeout_seconds", 0))
        self._poll_offset: int | None = _coerce_optional_int(
            config.params.get("initial_update_offset")
        )
        self._stop_polling = threading.Event()
        self._listener_thread: threading.Thread | None = None
        self._listener_error: Exception | None = None

    def send(self, message: OutboundMessage) -> DeliveryResult:
        try:
            message_id = _send_telegram_message(
                self.client,
                chat_id=self.chat_id,
                message=message,
            )
        except Exception as exc:  # noqa: BLE001 - platform API failures are result data.
            return DeliveryResult(
                success=False,
                platform=self.config.name,
                message_id=None,
                error=str(exc),
            )

        return DeliveryResult(
            success=True,
            platform=self.config.name,
            message_id=str(message_id),
        )

    def start_listener(
        self,
        on_message: InboundCallback,
        on_feedback: FeedbackCallback,
    ) -> None:
        if self._listener_thread is not None and self._listener_thread.is_alive():
            return
        if not _supports_telegram_polling(self.client):
            raise PlatformConnectionError(
                "telegram client does not expose a supported polling method"
            )

        self._listener_error = None
        self._stop_polling.clear()
        self._listener_thread = threading.Thread(
            target=self._run_polling,
            args=(on_message, on_feedback),
            name=f"gateway-{self.config.name}-poller",
            daemon=True,
        )
        self._listener_thread.start()

    def stop_listener(self) -> None:
        self._stop_polling.set()
        stop_method = getattr(self.client, "stop_polling", None)
        if stop_method is not None:
            _resolve_awaitable(_invoke_flexible(stop_method, {}))
        if self._listener_thread is not None:
            self._listener_thread.join(timeout=1.0)
            self._listener_thread = None

    def _run_polling(
        self,
        on_message: InboundCallback,
        on_feedback: FeedbackCallback,
    ) -> None:
        while not self._stop_polling.is_set():
            try:
                events = _poll_telegram_events(
                    self.client,
                    platform=self.config.name,
                    offset=self._poll_offset,
                    timeout=self._poll_timeout_seconds,
                )
                for update in events.updates:
                    if self._stop_polling.is_set():
                        break
                    raw_update = _object_to_raw_dict(update)
                    if (update_id := _raw_update_id(raw_update)) is not None:
                        next_offset = update_id + 1
                        self._poll_offset = (
                            next_offset
                            if self._poll_offset is None
                            else max(self._poll_offset, next_offset)
                        )
                for message in events.messages:
                    if self._stop_polling.is_set():
                        break
                    on_message(message)
                for signal in events.feedback:
                    if self._stop_polling.is_set():
                        break
                    on_feedback(signal)
            except Exception as exc:  # noqa: BLE001 - keep background listener alive.
                self._listener_error = exc
                if self._stop_polling.wait(self._poll_interval_seconds):
                    break
                continue
            self._stop_polling.wait(self._poll_interval_seconds)


def fake_adapter_factory(config: PlatformConfig) -> GatewayAdapter:
    return FakeGatewayAdapter(config)


def log_adapter_factory(config: PlatformConfig) -> GatewayAdapter:
    return LogGatewayAdapter(config)


def default_telegram_client_factory(config: PlatformConfig) -> object:
    try:
        from toolkit.telegram_client import TelegramClient
    except ImportError as exc:
        raise PlatformConfigError("toolkit telegram client is unavailable") from exc

    bot_token = config.credentials["bot_token"]
    chat_id = config.params["chat_id"]
    allowed_chat_ids: list[int] | None = None
    try:
        allowed_chat_ids = [int(chat_id)]
    except (TypeError, ValueError):
        allowed_chat_ids = None
    return TelegramClient(bot_token=bot_token)


def telegram_adapter_factory(
    config: PlatformConfig,
    client_factory: TelegramClientFactory | None = None,
) -> GatewayAdapter:
    return TelegramGatewayAdapter(config, client_factory=client_factory)


def _send_telegram_message(
    client: object,
    *,
    chat_id: str,
    message: OutboundMessage,
) -> object:
    chat_id_value = _coerce_optional_int(chat_id) or chat_id
    reply_to = _coerce_optional_int(message.reply_to)

    if message.format == "markdown":
        return _send_telegram_api_message(
            client,
            chat_id=chat_id_value,
            text=message.content,
            reply_to=reply_to,
            parse_mode=str(message.metadata.get("parse_mode") or "MarkdownV2"),
            metadata=message.metadata,
        )

    if message.format == "telegraph":
        for method_name in (
            "send_telegraph",
            "send_telegraph_message",
            "send_long_message",
        ):
            method = getattr(client, method_name, None)
            if method is not None:
                return _extract_message_id(
                    _resolve_awaitable(
                        _invoke_flexible(
                            method,
                            {
                                "chat_id": chat_id_value,
                                "text": message.content,
                                "content": message.content,
                                "reply_to": reply_to,
                                "reply_to_message_id": reply_to,
                                **message.metadata,
                            },
                        )
                    )
                )
        raise RuntimeError(
            "telegram client does not expose a supported telegraph send method"
        )

    return _send_plain_telegram_message(
        client,
        chat_id=chat_id_value,
        text=message.content,
        reply_to=reply_to,
        metadata=message.metadata,
    )


def _send_plain_telegram_message(
    client: object,
    *,
    chat_id: object,
    text: str,
    reply_to: int | None,
    metadata: dict,
) -> object:
    method = getattr(client, "send_message", None)
    if method is not None:
        return _extract_message_id(
            _resolve_awaitable(
                _invoke_flexible(
                    method,
                    {
                        "chat_id": chat_id,
                        "text": text,
                        "reply_to": reply_to,
                        "reply_to_message_id": reply_to,
                        **metadata,
                    },
                )
            )
        )

    return _send_telegram_api_message(
        client,
        chat_id=chat_id,
        text=text,
        reply_to=reply_to,
        parse_mode=None,
        metadata=metadata,
    )


def _send_telegram_api_message(
    client: object,
    *,
    chat_id: object,
    text: str,
    reply_to: int | None,
    parse_mode: str | None,
    metadata: dict,
) -> object:
    method = getattr(client, "request_api", None)
    if method is None:
        raise RuntimeError("telegram client does not expose a supported send method")

    payload = {
        "chat_id": chat_id,
        "text": text,
        **{
            key: value
            for key, value in metadata.items()
            if key not in {"parse_mode", "intent_tag"} and value is not None
        },
    }
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode

    return _extract_message_id(
        _resolve_awaitable(
            _invoke_flexible(
                method,
                {
                    "method": "sendMessage",
                    "payload": payload,
                },
            )
        )
    )


def _supports_telegram_polling(client: object) -> bool:
    return any(
        getattr(client, method_name, None) is not None
        for method_name in ("get_updates", "poll_updates", "get_next_update")
    )


def _poll_telegram_inbound(
    client: object,
    *,
    platform: str,
    offset: int | None,
    timeout: int,
) -> list[InboundMessage]:
    return _poll_telegram_events(
        client,
        platform=platform,
        offset=offset,
        timeout=timeout,
    ).messages


class _TelegramPollEvents:
    def __init__(
        self,
        *,
        updates: list[object],
        messages: list[InboundMessage],
        feedback: list[FeedbackSignal],
    ) -> None:
        self.updates = updates
        self.messages = messages
        self.feedback = feedback


def _poll_telegram_events(
    client: object,
    *,
    platform: str,
    offset: int | None,
    timeout: int,
) -> _TelegramPollEvents:
    raw_updates = _fetch_telegram_updates(client, offset=offset, timeout=timeout)
    if raw_updates is None:
        return _TelegramPollEvents(updates=[], messages=[], feedback=[])
    if not isinstance(raw_updates, list):
        raw_updates = [raw_updates]

    normalizer = getattr(client, "normalize_updates", None)
    if normalizer is not None:
        normalized = _resolve_awaitable(
            _invoke_flexible(normalizer, {"raw_updates": raw_updates})
        )
        if isinstance(normalized, list):
            raw_updates = normalized

    messages: list[InboundMessage] = []
    feedback: list[FeedbackSignal] = []
    for update in raw_updates:
        message = _normalize_telegram_inbound(update, platform=platform)
        if message is not None:
            messages.append(message)
        feedback.extend(_normalize_telegram_feedback(update, platform=platform))
    return _TelegramPollEvents(
        updates=list(raw_updates),
        messages=messages,
        feedback=feedback,
    )


def _fetch_telegram_updates(
    client: object,
    *,
    offset: int | None,
    timeout: int,
) -> object:
    for method_name, kwargs in (
        (
            "get_updates",
            {"offset": offset, "timeout": timeout},
        ),
        (
            "poll_updates",
            {"offset": offset, "timeout": timeout},
        ),
        (
            "get_next_update",
            {},
        ),
    ):
        method = getattr(client, method_name, None)
        if method is None:
            continue
        return _resolve_awaitable(_invoke_flexible(method, kwargs))
    raise RuntimeError("telegram client does not expose a supported polling method")


def _normalize_telegram_inbound(
    update: object,
    *,
    platform: str,
) -> InboundMessage | None:
    raw = _object_to_raw_dict(update)
    if _has_attr(update, "message_text"):
        return _inbound_from_normalized_update(update, platform=platform, raw=raw)
    if not isinstance(update, Mapping):
        return None
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, Mapping):
        return None
    content = message.get("text")
    if not isinstance(content, str):
        content = message.get("caption")
    if not isinstance(content, str):
        return None
    message_id = _coerce_optional_int(message.get("message_id"))
    if message_id is None:
        return None

    sender = _telegram_sender(message.get("from"))
    timestamp = _telegram_timestamp(message.get("date"))
    reply_to = None
    reply_payload = message.get("reply_to_message")
    if isinstance(reply_payload, Mapping):
        reply_id = _coerce_optional_int(reply_payload.get("message_id"))
        if reply_id is not None:
            reply_to = str(reply_id)

    return InboundMessage(
        content=content,
        platform=platform,
        message_id=str(message_id),
        sender=sender,
        timestamp=timestamp,
        reply_to=reply_to,
        reactions=_telegram_reactions(message),
        raw=dict(update),
    )


def _normalize_telegram_feedback(
    update: object,
    *,
    platform: str,
) -> list[FeedbackSignal]:
    raw = _object_to_raw_dict(update)
    signals: list[FeedbackSignal] = []
    if isinstance(update, Mapping):
        reaction_payload = update.get("message_reaction")
        if isinstance(reaction_payload, Mapping):
            signal = _feedback_from_reaction_payload(
                reaction_payload,
                platform=platform,
                raw=raw,
            )
            if signal is not None:
                signals.append(signal)

        message = update.get("message")
        if isinstance(message, Mapping):
            reply_signal = _feedback_from_reply_message(
                message,
                platform=platform,
                raw=raw,
            )
            if reply_signal is not None:
                signals.append(reply_signal)

        edited_message = update.get("edited_message")
        if isinstance(edited_message, Mapping):
            edit_signal = _feedback_from_edited_message(
                edited_message,
                platform=platform,
                raw=raw,
            )
            if edit_signal is not None:
                signals.append(edit_signal)
    elif _has_attr(update, "feedback_type"):
        signal = _feedback_from_normalized_update(update, platform=platform, raw=raw)
        if signal is not None:
            signals.append(signal)
    return signals


def _feedback_from_reaction_payload(
    payload: Mapping,
    *,
    platform: str,
    raw: dict | None,
) -> FeedbackSignal | None:
    message_id = _coerce_optional_int(payload.get("message_id"))
    if message_id is None:
        return None
    values = _telegram_reaction_values(payload.get("new_reaction"))
    if not values:
        values = _telegram_reaction_values(payload.get("reaction"))
    value = ",".join(values) if values else None
    return _with_raw_feedback(
        FeedbackSignal(
            platform=platform,
            message_id=str(message_id),
            signal_type="reaction",
            value=value,
            sender=_telegram_sender(payload.get("user")),
            timestamp=_telegram_timestamp(payload.get("date")),
        ),
        raw,
    )


def _feedback_from_reply_message(
    message: Mapping,
    *,
    platform: str,
    raw: dict | None,
) -> FeedbackSignal | None:
    reply_payload = message.get("reply_to_message")
    if not isinstance(reply_payload, Mapping):
        return None
    replied_id = _coerce_optional_int(reply_payload.get("message_id"))
    if replied_id is None:
        return None
    value = message.get("text")
    if not isinstance(value, str):
        value = message.get("caption")
    return _with_raw_feedback(
        FeedbackSignal(
            platform=platform,
            message_id=str(replied_id),
            signal_type="reply",
            value=value if isinstance(value, str) else None,
            sender=_telegram_sender(message.get("from")),
            timestamp=_telegram_timestamp(message.get("date")),
        ),
        raw,
    )


def _feedback_from_edited_message(
    message: Mapping,
    *,
    platform: str,
    raw: dict | None,
) -> FeedbackSignal | None:
    message_id = _coerce_optional_int(message.get("message_id"))
    if message_id is None:
        return None
    value = message.get("text")
    if not isinstance(value, str):
        value = message.get("caption")
    return _with_raw_feedback(
        FeedbackSignal(
            platform=platform,
            message_id=str(message_id),
            signal_type="edit",
            value=value if isinstance(value, str) else None,
            sender=_telegram_sender(message.get("from")),
            timestamp=_telegram_timestamp(
                message.get("edit_date")
                if message.get("edit_date") is not None
                else message.get("date")
            ),
        ),
        raw,
    )


def _feedback_from_normalized_update(
    update: object,
    *,
    platform: str,
    raw: dict | None,
) -> FeedbackSignal | None:
    message_id = getattr(update, "message_id", None)
    signal_type = getattr(update, "feedback_type", None)
    sender = getattr(update, "user_id", None)
    if message_id is None or not isinstance(signal_type, str) or sender is None:
        return None
    return _with_raw_feedback(
        FeedbackSignal(
            platform=platform,
            message_id=str(message_id),
            signal_type=signal_type,
            value=getattr(update, "value", None),
            sender=str(sender),
            timestamp=_telegram_timestamp(_field_from_raw(raw, "date")),
        ),
        raw,
    )


def _with_raw_feedback(
    signal: FeedbackSignal,
    raw: dict | None,
) -> FeedbackSignal:
    signal.raw = raw
    return signal


def _inbound_from_normalized_update(
    update: object,
    *,
    platform: str,
    raw: dict | None,
) -> InboundMessage | None:
    content = getattr(update, "message_text", None)
    message_id = getattr(update, "message_id", None)
    sender = getattr(update, "user_id", None)
    if not isinstance(content, str) or message_id is None or sender is None:
        return None
    return InboundMessage(
        content=content,
        platform=platform,
        message_id=str(message_id),
        sender=str(sender),
        timestamp=_telegram_timestamp(_field_from_raw(raw, "date")),
        reply_to=None,
        reactions=None,
        raw=raw,
    )


def _object_to_raw_dict(value: object) -> dict | None:
    if isinstance(value, Mapping):
        return dict(value)
    raw = getattr(value, "raw", None)
    if isinstance(raw, Mapping):
        return dict(raw)
    return None


def _field_from_raw(raw: dict | None, key: str) -> object:
    if not raw:
        return None
    message = raw.get("message")
    if isinstance(message, Mapping):
        return message.get(key)
    return raw.get(key)


def _telegram_sender(sender_payload: object) -> str:
    if not isinstance(sender_payload, Mapping):
        return "unknown"
    for key in ("username", "id", "first_name"):
        value = sender_payload.get(key)
        if value is not None and value != "":
            return str(value)
    return "unknown"


def _telegram_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    return datetime.now(UTC)


def _telegram_reactions(message: Mapping) -> list[str] | None:
    raw_reactions = message.get("reactions") or message.get("reaction")
    if raw_reactions is None:
        return None
    return _telegram_reaction_values(raw_reactions) or None


def _telegram_reaction_values(raw_reactions: object) -> list[str]:
    if isinstance(raw_reactions, str):
        return [raw_reactions]
    if isinstance(raw_reactions, list):
        reactions: list[str] = []
        for reaction in raw_reactions:
            if isinstance(reaction, str):
                reactions.append(reaction)
            elif isinstance(reaction, Mapping):
                value = reaction.get("emoji") or reaction.get("type")
                if isinstance(value, Mapping):
                    value = value.get("emoji") or value.get("type")
                if value is not None:
                    reactions.append(str(value))
        return reactions
    if isinstance(raw_reactions, Mapping):
        value = raw_reactions.get("emoji") or raw_reactions.get("type")
        if isinstance(value, Mapping):
            value = value.get("emoji") or value.get("type")
        if value is not None:
            return [str(value)]
    return []


def _raw_update_id(raw: dict | None) -> int | None:
    if not raw:
        return None
    return _coerce_optional_int(raw.get("update_id"))


def _has_attr(value: object, name: str) -> bool:
    return getattr(value, name, None) is not None


def _invoke_flexible(method: object, kwargs: dict[str, object]) -> object:
    assert callable(method)
    signature = inspect.signature(method)
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return method(**kwargs)
    supported_kwargs = {
        key: value for key, value in kwargs.items() if key in signature.parameters
    }
    return method(**supported_kwargs)


def _resolve_awaitable(value: object) -> object:
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)
    raise RuntimeError("telegram client returned awaitable inside a running event loop")


def _extract_message_id(result: object) -> object:
    if isinstance(result, dict):
        response_result = result.get("result")
        if isinstance(response_result, dict) and "message_id" in response_result:
            return response_result["message_id"]
        if "message_id" in result:
            return result["message_id"]
    message_id = getattr(result, "message_id", None)
    if message_id is not None:
        return message_id
    return result


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


DEFAULT_ADAPTER_REGISTRY = AdapterRegistry(
    {
        "fake": fake_adapter_factory,
        "log": log_adapter_factory,
        "telegram": telegram_adapter_factory,
    }
)
