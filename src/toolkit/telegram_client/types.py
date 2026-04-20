"""Telegram client data types and error classes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class TelegramClientError(Exception):
    """Base class for Telegram client failures."""


class TelegramAPIError(TelegramClientError):
    """Raised when Telegram returns an unsuccessful API response."""


@dataclass(frozen=True)
class TelegramUpdate:
    """Normalized Telegram update."""

    chat_id: int
    user_id: int
    message_text: str
    command: str | None
    args: tuple[str, ...]
    message_id: int
    raw: dict[str, Any]


@dataclass(frozen=True)
class SendResult:
    """Result of a send or edit operation."""

    success: bool
    message_id: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class InlineButton:
    """One button in an inline keyboard row."""

    text: str
    callback_data: str


@dataclass(frozen=True)
class InlineKeyboard:
    """Inline keyboard layout for Telegram messages."""

    rows: tuple[tuple[InlineButton, ...], ...]

    def to_markup(self) -> dict[str, Any]:
        """Convert to Telegram reply_markup dict."""
        return {
            "inline_keyboard": [
                [{"text": btn.text, "callback_data": btn.callback_data} for btn in row]
                for row in self.rows
            ]
        }
