"""Telegram Bot API client — public API."""

from .client import TelegramClient
from .formatting import (
    CONTINUATION_PREFIX,
    TELEGRAM_MESSAGE_LIMIT,
    escape_markdown,
    escape_url,
    format_link,
    split_message,
)
from .transport import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    TELEGRAM_API_BASE_URL,
    HTTPSTransport,
    TelegramTransport,
)
from .types import (
    InlineButton,
    InlineKeyboard,
    SendResult,
    TelegramAPIError,
    TelegramClientError,
    TelegramUpdate,
)

__all__ = [
    "CONTINUATION_PREFIX",
    "HTTPSTransport",
    "InlineButton",
    "InlineKeyboard",
    "SendResult",
    "TELEGRAM_API_BASE_URL",
    "TELEGRAM_MESSAGE_LIMIT",
    "TelegramAPIError",
    "TelegramClient",
    "TelegramClientError",
    "TelegramTransport",
    "TelegramUpdate",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "escape_markdown",
    "escape_url",
    "format_link",
    "split_message",
]
