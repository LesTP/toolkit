"""Human-curated share source adapter."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import re

from toolkit.source_ingestion.adapters import (
    AdapterItemError,
    AdapterPollResult,
    LastSeenMarker,
)
from toolkit.source_ingestion.normalization import (
    build_content_item,
    extract_urls,
    fetch_url_text,
    is_marker_newer,
    marker_sort_key,
)
from toolkit.source_ingestion.types import AdapterConfig, ContentItem, IngestionConfig


@dataclass
class _ShareMessage:
    marker: LastSeenMarker
    timestamp: datetime
    text: str
    author: str | None = None


class HumanShareAdapter:
    """Poll human-shared messages from a dedicated Telegram bot chat."""

    def __init__(self, config: AdapterConfig, ingestion_config: IngestionConfig) -> None:
        self.config = config
        self.ingestion_config = ingestion_config
        self.bot_chat_id = str(config.params["bot_chat_id"])
        self.bot_token = str((config.credentials or {})["bot_token"])
        self.telegram_client: object | None = None

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        if self.telegram_client is None:
            self.telegram_client = _create_telegram_client(self.bot_token)
        messages = _fetch_chat_messages(
            self.telegram_client,
            chat_id=self.bot_chat_id,
            last_seen_marker=last_seen_marker,
        )

        items: list[ContentItem] = []
        errors: list[AdapterItemError] = []
        newest_marker = last_seen_marker

        for message in sorted(messages, key=lambda item: marker_sort_key(item.marker)):
            if not is_marker_newer(message.marker, last_seen_marker):
                continue
            item, item_errors = _content_item_from_share(
                message=message,
                ingestion_config=self.ingestion_config,
            )
            if item is not None:
                items.append(item)
            errors.extend(item_errors)
            if is_marker_newer(message.marker, newest_marker):
                newest_marker = message.marker

        return AdapterPollResult(items=items, errors=errors, next_marker=newest_marker)


def human_share_adapter_factory(
    config: AdapterConfig, ingestion_config: IngestionConfig
) -> HumanShareAdapter:
    return HumanShareAdapter(config, ingestion_config)


def _create_telegram_client(bot_token: str) -> object:
    from toolkit.telegram_client import TelegramClient  # type: ignore[import-not-found]

    return TelegramClient(bot_token)


def _fetch_chat_messages(
    client: object, *, chat_id: str, last_seen_marker: LastSeenMarker
) -> list[_ShareMessage]:
    raw_messages = _call_supported_message_method(client, chat_id, last_seen_marker)
    return [
        message
        for raw_message in raw_messages
        if (message := _normalize_message(raw_message, chat_id)) is not None
    ]


def _call_supported_message_method(
    client: object, chat_id: str, last_seen_marker: LastSeenMarker
) -> Iterable[object]:
    method_specs = (
        ("poll_chat_messages", {"chat_id": chat_id, "offset": last_seen_marker}),
        ("get_chat_messages", {"chat_id": chat_id, "offset": last_seen_marker}),
        ("get_messages", {"chat_id": chat_id, "offset": last_seen_marker}),
        ("poll_messages", {"chat_id": chat_id, "offset": last_seen_marker}),
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

    raise RuntimeError("telegram client does not expose a supported polling method")


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

    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)
    raise RuntimeError("telegram client returned awaitable inside a running event loop")


def _normalize_message(raw_message: object, expected_chat_id: str) -> _ShareMessage | None:
    raw_message = _field(raw_message, "message") or raw_message
    if _message_chat_id(raw_message) not in {None, expected_chat_id}:
        return None

    text = _message_text(raw_message)
    if not text:
        return None

    timestamp = _message_timestamp(raw_message)
    marker = _message_marker(raw_message, timestamp)
    return _ShareMessage(
        marker=marker,
        timestamp=timestamp,
        text=text,
        author=_message_author(raw_message),
    )


def _content_item_from_share(
    *, message: _ShareMessage, ingestion_config: IngestionConfig
) -> tuple[ContentItem | None, list[AdapterItemError]]:
    urls = extract_urls(message.text)
    if not urls:
        return (
            build_content_item(
                content=message.text,
                source="human_share",
                timestamp=message.timestamp,
                config=ingestion_config,
                author=message.author,
            ),
            [],
        )

    primary_url = urls[0]
    annotation = _strip_urls(message.text).strip() or None
    errors: list[AdapterItemError] = []

    try:
        fetched = fetch_url_text(
            primary_url, ingestion_config.fetch_timeout.total_seconds()
        )
    except Exception as exc:  # noqa: BLE001 - URL failures are per-item.
        errors.append(AdapterItemError(error=str(exc), url=primary_url))
        fallback_content = annotation or primary_url
        title = f"Shared URL {primary_url}"
        linked_urls = urls
    else:
        fallback_content = fetched.text or annotation or primary_url
        title = fetched.title
        linked_urls = [*urls, *(fetched.linked_urls or [])]

    return (
        build_content_item(
            content=fallback_content,
            source="human_share",
            timestamp=message.timestamp,
            config=ingestion_config,
            url=primary_url,
            linked_urls=linked_urls,
            title=title,
            author=message.author,
            human_annotation=annotation,
        ),
        errors,
    )


def _message_text(raw_message: object) -> str:
    text = _field(raw_message, "text") or _field(raw_message, "caption")
    if text is None:
        return ""
    return str(text).strip()


def _message_marker(
    raw_message: object, timestamp: datetime
) -> str | int | float | datetime | None:
    for key in ("message_id", "id", "update_id"):
        value = _field(raw_message, key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float | str) and value != "":
            return value
    return timestamp


def _message_timestamp(raw_message: object) -> datetime:
    value = _field(raw_message, "date") or _field(raw_message, "timestamp")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(
            tzinfo=timezone.utc
        )
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value), timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
        else:
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(
                tzinfo=timezone.utc
            )
    return datetime.now(timezone.utc)


def _message_chat_id(raw_message: object) -> str | None:
    chat = _field(raw_message, "chat")
    chat_id = _field(chat, "id") if chat is not None else _field(raw_message, "chat_id")
    return str(chat_id) if chat_id is not None else None


def _message_author(raw_message: object) -> str | None:
    sender = _field(raw_message, "from_user") or _field(raw_message, "from")
    if sender is not None:
        author = _field(sender, "username") or _field(sender, "name") or _field(
            sender, "first_name"
        )
        if author:
            return str(author)
    author = _field(raw_message, "author") or _field(raw_message, "sender")
    return str(author) if author else None


def _field(value: object, key: str) -> object | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _strip_urls(text: str) -> str:
    return re.sub(r"https?://\S+", "", text).strip()


def _numeric_offset(marker: LastSeenMarker) -> int | None:
    if isinstance(marker, bool):
        return None
    if isinstance(marker, int | float):
        return int(marker) + 1
    if isinstance(marker, str) and marker.isdigit():
        return int(marker) + 1
    return None
