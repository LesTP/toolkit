"""Tests for TelegramClient.send_message auto-chunking — Phase 32.2.

Verifies that ``send_message`` transparently splits oversized text into
multiple ``sendMessage`` API calls while preserving its single-shot
behavior for text within the 4096-char limit.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

import pytest

from toolkit.telegram_client import (
    CONTINUATION_PREFIX,
    TELEGRAM_MESSAGE_LIMIT,
    TelegramClient,
    TelegramTransport,
)


class _RecordingTransport(TelegramTransport):
    """Captures every API call and returns a scripted message_id sequence."""

    def __init__(self, message_ids: list[int] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._ids = list(message_ids) if message_ids else [1001]
        self._next = 0

    async def request(
        self,
        bot_token: str,
        method: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append((method, dict(payload)))
        if self._next < len(self._ids):
            msg_id = self._ids[self._next]
        else:
            msg_id = self._ids[-1] + (self._next - len(self._ids) + 1)
        self._next += 1
        return {"ok": True, "result": {"message_id": msg_id}}


def _build_client(transport: _RecordingTransport) -> TelegramClient:
    return TelegramClient("bot-token-xyz", transport=transport)


# ---------------------------------------------------------------------------
# Short text — single-shot path is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_text_makes_exactly_one_api_call():
    transport = _RecordingTransport(message_ids=[7001])
    client = _build_client(transport)

    msg_id = await client.send_message(chat_id=12345, text="hello world")

    assert msg_id == 7001
    assert len(transport.calls) == 1
    method, payload = transport.calls[0]
    assert method == "sendMessage"
    assert payload == {"chat_id": 12345, "text": "hello world"}


@pytest.mark.asyncio
async def test_text_exactly_at_limit_is_single_call():
    transport = _RecordingTransport(message_ids=[7002])
    client = _build_client(transport)
    text = "x" * TELEGRAM_MESSAGE_LIMIT

    msg_id = await client.send_message(chat_id=12345, text=text)

    assert msg_id == 7002
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_short_text_with_reply_to_carries_reply_field():
    transport = _RecordingTransport(message_ids=[7003])
    client = _build_client(transport)

    await client.send_message(chat_id=12345, text="hi", reply_to=999)

    payload = transport.calls[0][1]
    assert payload["reply_to_message_id"] == 999


# ---------------------------------------------------------------------------
# Oversized text — auto-chunking path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oversized_text_triggers_multiple_api_calls():
    transport = _RecordingTransport(message_ids=[8001, 8002, 8003])
    client = _build_client(transport)
    text = "x" * (TELEGRAM_MESSAGE_LIMIT + 1000)

    msg_id = await client.send_message(chat_id=42, text=text)

    assert len(transport.calls) >= 2
    assert all(call[0] == "sendMessage" for call in transport.calls)
    # Returns the LAST message_id (preserves int return type)
    assert msg_id == 8000 + len(transport.calls)


@pytest.mark.asyncio
async def test_oversized_text_all_chunks_target_same_chat_and_within_limit():
    transport = _RecordingTransport()
    client = _build_client(transport)
    text = "x" * (TELEGRAM_MESSAGE_LIMIT * 3 + 100)

    await client.send_message(chat_id=42, text=text)

    assert len(transport.calls) >= 3
    for method, payload in transport.calls:
        assert method == "sendMessage"
        assert payload["chat_id"] == 42
        assert len(payload["text"]) <= TELEGRAM_MESSAGE_LIMIT


@pytest.mark.asyncio
async def test_oversized_text_continuation_marker_on_chunks_2_plus():
    transport = _RecordingTransport()
    client = _build_client(transport)
    text = "x" * (TELEGRAM_MESSAGE_LIMIT + 500)

    await client.send_message(chat_id=42, text=text)

    chunks_text = [payload["text"] for _, payload in transport.calls]
    assert not chunks_text[0].startswith(CONTINUATION_PREFIX), \
        "first chunk should never carry the continuation marker"
    for chunk in chunks_text[1:]:
        assert chunk.startswith(CONTINUATION_PREFIX), \
            f"chunk 2+ should start with CONTINUATION_PREFIX, got: {chunk[:40]!r}"


@pytest.mark.asyncio
async def test_oversized_text_reply_to_only_on_first_chunk():
    """``reply_to_message_id`` is a reply to a specific message — applying it
    to every chunk would attach all chunks as replies, which is wrong UX.
    Only the FIRST chunk is the reply; subsequent chunks are continuations.
    """
    transport = _RecordingTransport()
    client = _build_client(transport)
    text = "x" * (TELEGRAM_MESSAGE_LIMIT + 500)

    await client.send_message(chat_id=42, text=text, reply_to=777)

    assert len(transport.calls) >= 2
    first_payload = transport.calls[0][1]
    assert first_payload["reply_to_message_id"] == 777
    for _, payload in transport.calls[1:]:
        assert "reply_to_message_id" not in payload


@pytest.mark.asyncio
async def test_oversized_text_parse_mode_applied_to_every_chunk():
    """Unlike reply_to, parse_mode is a per-message rendering rule — must
    apply to every chunk so all parts render with the same Markdown/HTML
    handling."""
    transport = _RecordingTransport()
    client = _build_client(transport)
    text = "x" * (TELEGRAM_MESSAGE_LIMIT + 500)

    await client.send_message(chat_id=42, text=text, parse_mode="MarkdownV2")

    assert len(transport.calls) >= 2
    for _, payload in transport.calls:
        assert payload["parse_mode"] == "MarkdownV2"


@pytest.mark.asyncio
async def test_oversized_text_logs_chunk_count_at_info_level(caplog):
    transport = _RecordingTransport()
    client = _build_client(transport)
    text = "x" * (TELEGRAM_MESSAGE_LIMIT + 500)

    with caplog.at_level(logging.INFO, logger="toolkit.telegram_client.client"):
        await client.send_message(chat_id=42, text=text)

    chunked_records = [
        rec for rec in caplog.records if "chunked" in rec.getMessage()
    ]
    assert len(chunked_records) == 1
    assert "parts" in chunked_records[0].getMessage()


@pytest.mark.asyncio
async def test_short_text_does_not_log_chunked_message(caplog):
    transport = _RecordingTransport()
    client = _build_client(transport)

    with caplog.at_level(logging.INFO, logger="toolkit.telegram_client.client"):
        await client.send_message(chat_id=42, text="short")

    chunked_records = [
        rec for rec in caplog.records if "chunked" in rec.getMessage()
    ]
    assert chunked_records == []


# ---------------------------------------------------------------------------
# Input validation — type check still fires, but length check no longer does
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_rejects_non_string_text():
    transport = _RecordingTransport()
    client = _build_client(transport)

    with pytest.raises(TypeError):
        await client.send_message(chat_id=42, text=b"bytes")  # type: ignore[arg-type]
    assert transport.calls == []


# ---------------------------------------------------------------------------
# edit_message + send_with_keyboard still enforce the 4096 limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_message_still_rejects_oversize():
    transport = _RecordingTransport()
    client = _build_client(transport)

    with pytest.raises(ValueError):
        await client.edit_message(
            chat_id=42, message_id=1, text="x" * (TELEGRAM_MESSAGE_LIMIT + 1)
        )
    assert transport.calls == []
