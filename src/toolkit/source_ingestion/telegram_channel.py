"""Telegram channel source adapter."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from toolkit.source_ingestion.adapters import (
    AdapterItemError,
    AdapterPollResult,
    LastSeenMarker,
)
from toolkit.source_ingestion.human_share import (
    _field,
    _invoke_flexible,
    _message_author,
    _message_marker,
    _message_timestamp,
    _numeric_offset,
    _resolve_awaitable,
)
from toolkit.source_ingestion.normalization import (
    build_content_item,
    is_marker_newer,
    marker_sort_key,
)
from toolkit.source_ingestion.types import AdapterConfig, ContentItem, IngestionConfig


@dataclass
class _ChannelMessage:
    marker: LastSeenMarker
    timestamp: datetime
    content: str
    author: str | None = None
    title: str | None = None


class TelegramChannelAdapter:
    """Poll a Telegram channel via the toolkit Telegram client boundary."""

    def __init__(self, config: AdapterConfig, ingestion_config: IngestionConfig) -> None:
        self.config = config
        self.ingestion_config = ingestion_config
        self.bot_token = str((config.credentials or {})["bot_token"])
        self.channel_id = _optional_str(config.params.get("channel_id"))
        self.channel_username = _optional_str(config.params.get("channel_username"))
        self.telegram_client: object | None = None

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        if self.telegram_client is None:
            self.telegram_client = _create_telegram_client(self.bot_token)

        try:
            messages = _fetch_channel_messages(
                self.telegram_client,
                channel_id=self.channel_id,
                channel_username=self.channel_username,
                last_seen_marker=last_seen_marker,
            )
        except Exception as exc:  # noqa: BLE001 - API failures stay in result errors.
            return AdapterPollResult(
                errors=[AdapterItemError(error=str(exc))],
                next_marker=last_seen_marker,
            )

        items: list[ContentItem] = []
        newest_marker = last_seen_marker
        for message in sorted(messages, key=lambda item: marker_sort_key(item.marker)):
            if not is_marker_newer(message.marker, last_seen_marker):
                continue
            items.append(
                build_content_item(
                    content=message.content,
                    source="telegram_channel",
                    timestamp=message.timestamp,
                    config=self.ingestion_config,
                    title=message.title,
                    author=message.author,
                )
            )
            if is_marker_newer(message.marker, newest_marker):
                newest_marker = message.marker

        return AdapterPollResult(items=items, next_marker=newest_marker)


def telegram_channel_adapter_factory(
    config: AdapterConfig, ingestion_config: IngestionConfig
) -> TelegramChannelAdapter:
    return TelegramChannelAdapter(config, ingestion_config)


def _create_telegram_client(bot_token: str) -> object:
    from toolkit.telegram_client import TelegramClient  # type: ignore[import-not-found]

    return TelegramClient(bot_token)


def _fetch_channel_messages(
    client: object,
    *,
    channel_id: str | None,
    channel_username: str | None,
    last_seen_marker: LastSeenMarker,
) -> list[_ChannelMessage]:
    raw_messages = _call_supported_channel_method(
        client,
        channel_id=channel_id,
        channel_username=channel_username,
        last_seen_marker=last_seen_marker,
    )
    return [
        message
        for raw_message in raw_messages
        if (
            message := _normalize_channel_message(
                raw_message,
                expected_channel_id=channel_id,
                expected_channel_username=channel_username,
            )
        )
        is not None
    ]


def _call_supported_channel_method(
    client: object,
    *,
    channel_id: str | None,
    channel_username: str | None,
    last_seen_marker: LastSeenMarker,
) -> Iterable[object]:
    channel = channel_username or channel_id
    method_specs = (
        (
            "poll_channel_messages",
            {
                "channel_id": channel_id,
                "channel_username": channel_username,
                "offset": last_seen_marker,
            },
        ),
        (
            "get_channel_messages",
            {
                "channel_id": channel_id,
                "channel_username": channel_username,
                "offset": last_seen_marker,
            },
        ),
        ("get_messages", {"chat_id": channel, "offset": last_seen_marker}),
        ("poll_messages", {"chat_id": channel, "offset": last_seen_marker}),
        ("get_updates", {"offset": _numeric_offset(last_seen_marker), "timeout": 0}),
    )

    for method_name, kwargs in method_specs:
        method = getattr(client, method_name, None)
        if method is None:
            continue
        try:
            result = _invoke_flexible(method, kwargs)
        except TypeError:
            continue
        return _resolve_awaitable(result) or []

    raise RuntimeError("telegram client does not expose a supported channel polling method")


def _normalize_channel_message(
    raw_message: object,
    *,
    expected_channel_id: str | None,
    expected_channel_username: str | None,
) -> _ChannelMessage | None:
    raw_message = _field(raw_message, "channel_post") or _field(raw_message, "message") or raw_message
    if not _matches_channel(raw_message, expected_channel_id, expected_channel_username):
        return None

    content = _message_content(raw_message)
    if not content:
        return None

    timestamp = _message_timestamp(raw_message)
    marker = _message_marker(raw_message, timestamp)
    return _ChannelMessage(
        marker=marker,
        timestamp=timestamp,
        content=content,
        author=_message_author(raw_message),
        title=_field_as_str(raw_message, "title"),
    )


def _matches_channel(
    raw_message: object,
    expected_channel_id: str | None,
    expected_channel_username: str | None,
) -> bool:
    chat = _field(raw_message, "chat")
    chat_id = _field(chat, "id") if chat is not None else _field(raw_message, "chat_id")
    username = _field(chat, "username") if chat is not None else _field(raw_message, "channel_username")

    if expected_channel_id is not None and chat_id is not None:
        return str(chat_id) == expected_channel_id
    if expected_channel_username is not None and username is not None:
        return _normalize_username(str(username)) == _normalize_username(expected_channel_username)
    return True


def _message_content(raw_message: object) -> str:
    chunks = [
        _field_as_str(raw_message, "text"),
        _field_as_str(raw_message, "caption"),
        _forwarded_text(raw_message),
    ]
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _forwarded_text(raw_message: object) -> str | None:
    forwarded = (
        _field(raw_message, "forwarded_message")
        or _field(raw_message, "forward")
        or _field(raw_message, "forward_from_message")
    )
    if forwarded is not None:
        return _message_content(forwarded)
    return _field_as_str(raw_message, "forward_text") or _field_as_str(
        raw_message, "forwarded_text"
    )


def _field_as_str(value: object, key: str) -> str | None:
    field_value = _field(value, key)
    if field_value is None:
        return None
    text = str(field_value).strip()
    return text or None


def _normalize_username(username: str) -> str:
    return username.removeprefix("@").lower()


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None and value != "" else None
