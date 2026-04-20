"""Telegram Bot API transport layer."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping, Protocol
from urllib import error as urlerror
from urllib import request as urlrequest

from .types import TelegramAPIError


DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
TELEGRAM_API_BASE_URL = "https://api.telegram.org"


class TelegramTransport(Protocol):
    """Async boundary for Telegram Bot API calls."""

    async def request(
        self, bot_token: str, method: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Send one Telegram Bot API request and return the decoded response."""


class HTTPSTransport:
    """Direct HTTPS transport for Telegram Bot API JSON requests."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        base_url: str = TELEGRAM_API_BASE_URL,
    ) -> None:
        self.timeout_seconds = float(timeout_seconds)
        self.base_url = base_url.rstrip("/")

    async def request(
        self, bot_token: str, method: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._request_sync, bot_token, method, dict(payload)
        )

    def _request_sync(
        self, bot_token: str, method: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            f"{self.base_url}/bot{bot_token}/{method}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlrequest.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_body = response.read()
        except urlerror.HTTPError as exc:
            raw_body = exc.read()
            if 500 <= exc.code < 600:
                raise ConnectionError(f"Telegram HTTP {exc.code}") from exc
            try:
                decoded = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise TelegramAPIError(f"Telegram HTTP {exc.code}") from exc
            if isinstance(decoded, dict):
                return decoded
            raise TelegramAPIError(f"Telegram HTTP {exc.code}") from exc
        except (OSError, TimeoutError, urlerror.URLError) as exc:
            raise ConnectionError("Telegram API request failed") from exc

        try:
            decoded = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConnectionError("Telegram API returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise ConnectionError("Telegram API returned a non-object response")
        return decoded
