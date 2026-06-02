from datetime import datetime, timezone

import pytest

import toolkit.source_ingestion.human_share as human_share_module
from toolkit.source_ingestion import AdapterConfig, IngestionConfig, SourceIngestion
from toolkit.source_ingestion.normalization import PageFetchResult


class FakeTelegramClient:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = messages
        self.calls: list[dict[str, object]] = []

    def get_messages(self, chat_id: str, offset: object | None = None) -> list[dict]:
        self.calls.append({"chat_id": chat_id, "offset": offset})
        return self.messages


def _manager(messages: list[dict], monkeypatch: pytest.MonkeyPatch) -> SourceIngestion:
    client = FakeTelegramClient(messages)
    monkeypatch.setattr(
        human_share_module, "_create_telegram_client", lambda bot_token: client
    )
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="human_share",
                    source_label="shares",
                    credentials={"bot_token": "token"},
                    params={"bot_chat_id": "12345"},
                )
            ]
        )
    )
    manager.fake_client = client  # type: ignore[attr-defined]
    return manager


def test_human_share_url_only_fetches_page_and_advances_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(
        [
            {
                "message_id": 10,
                "chat": {"id": "12345"},
                "date": "2026-05-04T10:00:00Z",
                "text": "https://example.com/article",
            }
        ],
        monkeypatch,
    )

    def fake_fetch(url: str, timeout_seconds: float) -> PageFetchResult:
        assert url == "https://example.com/article"
        assert timeout_seconds == 30
        return PageFetchResult(
            url=url,
            text="Fetched body",
            title="Fetched Title",
            linked_urls=["https://example.com/next"],
        )

    monkeypatch.setattr(human_share_module, "fetch_url_text", fake_fetch)

    first = manager.poll_once("shares")
    second = manager.poll_once("shares")

    assert first.errors == []
    assert len(first.items) == 1
    item = first.items[0]
    assert item.source == "human_share"
    assert item.content == "Fetched body"
    assert item.url == "https://example.com/article"
    assert item.linked_urls == [
        "https://example.com/article",
        "https://example.com/next",
    ]
    assert item.title == "Fetched Title"
    assert item.human_annotation is None
    assert item.timestamp == datetime(2026, 5, 4, 10, tzinfo=timezone.utc)
    assert second.items == []
    assert manager.fake_client.calls == [  # type: ignore[attr-defined]
        {"chat_id": "12345", "offset": None},
        {"chat_id": "12345", "offset": 10},
    ]


def test_human_share_url_plus_text_preserves_annotation_and_extra_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(
        [
            {
                "message_id": 11,
                "chat": {"id": "12345"},
                "date": 1_777_777_777,
                "text": (
                    "This is the useful part https://example.com/article "
                    "and related https://example.com/related"
                ),
                "from_user": {"username": "human"},
            }
        ],
        monkeypatch,
    )
    monkeypatch.setattr(
        human_share_module,
        "fetch_url_text",
        lambda url, timeout_seconds: PageFetchResult(
            url=url, text="Fetched page", title=None, linked_urls=[]
        ),
    )

    result = manager.poll_once("shares")

    assert result.errors == []
    item = result.items[0]
    assert item.content == "Fetched page"
    assert item.human_annotation == "This is the useful part  and related"
    assert item.author == "human"
    assert item.linked_urls == [
        "https://example.com/article",
        "https://example.com/related",
    ]


def test_human_share_text_only_becomes_content_without_url_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(
        [
            {
                "message_id": 12,
                "chat": {"id": "12345"},
                "date": "2026-05-04T12:00:00Z",
                "text": "A direct note with no links.",
            }
        ],
        monkeypatch,
    )

    def fail_fetch(url: str, timeout_seconds: float) -> PageFetchResult:
        raise AssertionError("text-only shares should not fetch")

    monkeypatch.setattr(human_share_module, "fetch_url_text", fail_fetch)

    result = manager.poll_once("shares")

    assert result.errors == []
    assert result.items[0].content == "A direct note with no links."
    assert result.items[0].url is None
    assert result.items[0].linked_urls == []
    assert result.items[0].human_annotation is None


def test_human_share_fetch_failure_keeps_annotation_fallback_and_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(
        [
            {
                "message_id": 13,
                "chat": {"id": "12345"},
                "date": "2026-05-04T13:00:00Z",
                "text": "Worth saving https://example.com/missing",
            }
        ],
        monkeypatch,
    )

    def failing_fetch(url: str, timeout_seconds: float) -> PageFetchResult:
        raise OSError("network unavailable")

    monkeypatch.setattr(human_share_module, "fetch_url_text", failing_fetch)

    result = manager.poll_once("shares")

    assert result.items[0].content == "Worth saving"
    assert result.items[0].url == "https://example.com/missing"
    assert result.items[0].human_annotation == "Worth saving"
    assert result.items[0].linked_urls == ["https://example.com/missing"]
    assert result.errors[0].adapter_label == "shares"
    assert result.errors[0].url == "https://example.com/missing"
    assert result.errors[0].error == "network unavailable"


def test_human_share_ignores_other_chats(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _manager(
        [
            {
                "message_id": 14,
                "chat": {"id": "elsewhere"},
                "date": "2026-05-04T14:00:00Z",
                "text": "Do not ingest",
            }
        ],
        monkeypatch,
    )

    assert manager.poll_once("shares").items == []
