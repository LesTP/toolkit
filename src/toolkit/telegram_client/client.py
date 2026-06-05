"""Telegram Bot API client for sending, editing, and polling messages."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping

from .formatting import TELEGRAM_MESSAGE_LIMIT, split_message
from .transport import DEFAULT_REQUEST_TIMEOUT_SECONDS, HTTPSTransport, TelegramTransport
from .types import (
    InlineKeyboard,
    SendResult,
    TelegramAPIError,
    TelegramClientError,
    TelegramUpdate,
)


DEFAULT_POLL_TIMEOUT_SECONDS = 25.0
DEFAULT_POLL_RETRIES = 3
DEFAULT_REQUEST_RETRIES = DEFAULT_POLL_RETRIES
DEFAULT_RETRY_BACKOFF_SECONDS = 0.25
POLL_NETWORK_BACKOFF_SECONDS = 300

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class TelegramClient:
    """Client for Telegram long polling and outbound message operations."""

    def __init__(
        self,
        bot_token: str,
        *,
        transport: TelegramTransport | None = None,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        poll_timeout_seconds: float = DEFAULT_POLL_TIMEOUT_SECONDS,
    ) -> None:
        if not bot_token:
            raise ValueError("bot_token is required")

        self.bot_token = str(bot_token)
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.poll_timeout_seconds = float(poll_timeout_seconds)
        self.transport = transport or HTTPSTransport(
            timeout_seconds=self.request_timeout_seconds
        )
        self._polling = False
        self._update_offset: int | None = None
        self._stop_polling = asyncio.Event()
        self._update_queue: asyncio.Queue[TelegramUpdate | None] = asyncio.Queue()

    async def request_api(
        self, method: str, payload: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send one request through the configured Telegram transport."""
        if not method:
            raise ValueError("method is required")

        request_payload = dict(payload or {})
        last_error: ConnectionError | None = None
        for attempt in range(1, DEFAULT_REQUEST_RETRIES + 1):
            try:
                response = await self.transport.request(
                    self.bot_token, method, request_payload
                )
                break
            except TelegramAPIError:
                raise
            except ConnectionError as exc:
                last_error = exc
            except OSError as exc:
                last_error = ConnectionError("Telegram API request failed")
                last_error.__cause__ = exc

            if attempt < DEFAULT_REQUEST_RETRIES:
                LOGGER.warning(
                    "Telegram API request failed; retrying",
                    extra={"method": method, "attempt": attempt},
                    exc_info=(
                        type(last_error),
                        last_error,
                        last_error.__traceback__,
                    ),
                )
                await asyncio.sleep(DEFAULT_RETRY_BACKOFF_SECONDS * attempt)
        else:
            LOGGER.error(
                "Telegram API unreachable after retries",
                extra={"method": method, "attempts": DEFAULT_REQUEST_RETRIES},
            )
            raise ConnectionError("Telegram API unreachable after retries") from last_error

        if not response.get("ok", False):
            description = response.get("description") or "Telegram API request failed"
            raise TelegramAPIError(str(description))
        return response

    async def get_updates(
        self,
        *,
        offset: int | None = None,
        timeout: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch raw Telegram updates through the Bot API."""
        payload: dict[str, Any] = {
            "timeout": int(
                self.poll_timeout_seconds if timeout is None else timeout
            )
        }
        if offset is not None:
            payload["offset"] = int(offset)
        if limit is not None:
            payload["limit"] = int(limit)

        response = await self.request_api("getUpdates", payload)
        result = response.get("result", [])
        if not isinstance(result, list):
            raise TelegramAPIError("Telegram getUpdates returned invalid result")
        return result

    async def start_polling(self, *, initial_offset: int | None = None) -> None:
        """Start the cancellable long-poll loop until stopped or cancelled."""
        if initial_offset is not None:
            self._update_offset = int(initial_offset)
        self._polling = True
        self._stop_polling.clear()
        try:
            while not self._stop_polling.is_set():
                try:
                    updates = await self._poll_once()
                except (ConnectionError, OSError) as exc:
                    LOGGER.warning(
                        "Polling failed due to network error; "
                        "retrying in %d seconds",
                        POLL_NETWORK_BACKOFF_SECONDS,
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )
                    await self._interruptible_sleep(
                        POLL_NETWORK_BACKOFF_SECONDS
                    )
                    continue
                for update in updates:
                    self._update_queue.put_nowait(update)
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        finally:
            self._polling = False

    async def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep for *seconds*, returning early if stop_polling is set."""
        remaining = float(seconds)
        while remaining > 0 and not self._stop_polling.is_set():
            tick = min(remaining, 1.0)
            await asyncio.sleep(tick)
            remaining -= tick

    async def stop_polling(self) -> None:
        """Signal the polling loop to exit gracefully."""
        self._stop_polling.set()
        self._polling = False
        self._update_queue.put_nowait(None)

    async def get_next_update(self) -> TelegramUpdate | None:
        """Return the next normalized update, or None on timeout."""
        if not self._update_queue.empty():
            return await self._update_queue.get()

        if self._polling:
            try:
                return await asyncio.wait_for(
                    self._update_queue.get(),
                    timeout=self.poll_timeout_seconds,
                )
            except asyncio.TimeoutError:
                return None

        updates = await self._poll_once()
        if not updates:
            return None

        first, remaining = updates[0], updates[1:]
        for update in remaining:
            self._update_queue.put_nowait(update)
        return first

    @property
    def next_update_offset(self) -> int | None:
        """Return the next Telegram update offset known to the client."""
        return self._update_offset

    def normalize_update(self, raw_update: Mapping[str, Any]) -> TelegramUpdate | None:
        """Convert one raw Telegram message update into the internal update type.

        Malformed or unsupported updates return ``None``.
        """
        if not isinstance(raw_update, Mapping):
            return None

        message = raw_update.get("message")
        if not isinstance(message, Mapping):
            return None

        chat = message.get("chat")
        sender = message.get("from")
        text = message.get("text")
        if (
            not isinstance(chat, Mapping)
            or not isinstance(sender, Mapping)
            or not isinstance(text, str)
        ):
            return None

        chat_id = self._coerce_int(chat.get("id"))
        user_id = self._coerce_int(sender.get("id"))
        message_id = self._coerce_int(message.get("message_id"))
        if chat_id is None or user_id is None or message_id is None:
            return None

        command, args = self._parse_command(text)
        return TelegramUpdate(
            chat_id=chat_id,
            user_id=user_id,
            message_text=text,
            command=command,
            args=args,
            message_id=message_id,
            raw=dict(raw_update),
        )

    def normalize_updates(
        self, raw_updates: list[Mapping[str, Any]]
    ) -> list[TelegramUpdate]:
        """Normalize a raw getUpdates batch and advance past every seen update."""
        normalized: list[TelegramUpdate] = []
        for raw_update in raw_updates:
            if isinstance(raw_update, Mapping):
                update_id = self._coerce_int(raw_update.get("update_id"))
                if update_id is not None:
                    next_offset = update_id + 1
                    if self._update_offset is None:
                        self._update_offset = next_offset
                    else:
                        self._update_offset = max(self._update_offset, next_offset)

            update = self.normalize_update(raw_update)
            if update is not None:
                normalized.append(update)
        return normalized

    async def _poll_once(self) -> list[TelegramUpdate]:
        raw_updates = await self.get_updates(offset=self._update_offset)
        return self.normalize_updates(raw_updates)

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None,
        *,
        parse_mode: str | None = None,
    ) -> int:
        """Send a Telegram message and return the resulting message ID.

        Auto-chunks oversized text. If ``len(text) <= TELEGRAM_MESSAGE_LIMIT``
        a single API call is made and the message_id is returned, identical
        to the pre-Phase-32 behavior. If the text exceeds the limit, it is
        split via :func:`toolkit.telegram_client.split_message` (paragraph-
        first with ``[continued ...]`` markers) and sent as N serial
        ``sendMessage`` calls; the **last** message_id is returned to
        preserve the ``int`` return type for callers. ``reply_to`` is
        applied only to the FIRST chunk (subsequent chunks are continuations,
        not replies). ``parse_mode`` is applied to every chunk.
        """
        self._validate_text_type(text)

        if len(text) <= TELEGRAM_MESSAGE_LIMIT:
            payload: dict[str, Any] = {"chat_id": int(chat_id), "text": text}
            if reply_to is not None:
                payload["reply_to_message_id"] = int(reply_to)
            if parse_mode is not None:
                payload["parse_mode"] = parse_mode
            response = await self.request_api("sendMessage", payload)
            return self._extract_message_id(response)

        chunks = split_message(text, limit=TELEGRAM_MESSAGE_LIMIT)
        LOGGER.info(
            "send_message chunked into %d parts (chat_id=%s, total_chars=%d)",
            len(chunks),
            int(chat_id),
            len(text),
        )
        last_message_id: int | None = None
        for index, chunk in enumerate(chunks):
            payload = {"chat_id": int(chat_id), "text": chunk}
            if reply_to is not None and index == 0:
                payload["reply_to_message_id"] = int(reply_to)
            if parse_mode is not None:
                payload["parse_mode"] = parse_mode
            response = await self.request_api("sendMessage", payload)
            last_message_id = self._extract_message_id(response)
        assert last_message_id is not None  # split_message never returns []
        return last_message_id

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
    ) -> None:
        """Edit a Telegram message owned by the bot."""
        self._validate_message_text(text)

        payload: dict[str, Any] = {
            "chat_id": int(chat_id),
            "message_id": int(message_id),
            "text": text,
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode

        await self.request_api("editMessageText", payload)

    async def send_with_keyboard(
        self,
        chat_id: int,
        text: str,
        keyboard: InlineKeyboard,
        *,
        parse_mode: str | None = None,
    ) -> SendResult:
        """Send a message with an inline keyboard."""
        self._validate_message_text(text)

        payload: dict[str, Any] = {
            "chat_id": int(chat_id),
            "text": text,
            "reply_markup": keyboard.to_markup(),
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode

        response = await self.request_api("sendMessage", payload)
        msg_id = self._extract_message_id(response)
        return SendResult(success=True, message_id=msg_id)

    @staticmethod
    def _parse_command(text: str) -> tuple[str | None, tuple[str, ...]]:
        if not text.startswith("/"):
            return None, ()

        words = text.split()
        if not words or len(words[0]) == 1:
            return None, ()

        command = words[0][1:].split("@", 1)[0].lower()
        if not command:
            return None, ()
        return command, tuple(words[1:])

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _validate_text_type(text: str) -> None:
        """Type-only validation. Used by ``send_message`` which auto-chunks
        and therefore doesn't impose the 4096 hard limit on inputs."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")

    @staticmethod
    def _validate_message_text(text: str) -> None:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if len(text) > TELEGRAM_MESSAGE_LIMIT:
            raise ValueError("Telegram messages must be 4096 characters or fewer")

    @staticmethod
    def _extract_message_id(response: Mapping[str, Any]) -> int:
        result = response.get("result")
        if not isinstance(result, Mapping) or "message_id" not in result:
            raise TelegramAPIError("Telegram response did not include message_id")
        return int(result["message_id"])
