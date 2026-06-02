from datetime import datetime, timezone

import pytest

import toolkit.source_ingestion.reddit as reddit_module
import toolkit.source_ingestion.telegram_channel as telegram_module
from toolkit.source_ingestion import AdapterConfig, IngestionConfig, SourceIngestion


class FakeTelegramClient:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = messages
        self.calls: list[dict[str, object]] = []

    def get_channel_messages(
        self,
        channel_id: str | None = None,
        channel_username: str | None = None,
        offset: object | None = None,
    ) -> list[dict]:
        self.calls.append(
            {
                "channel_id": channel_id,
                "channel_username": channel_username,
                "offset": offset,
            }
        )
        return self.messages


class FakeRedditClient:
    def __init__(self, posts: list[dict] | Exception) -> None:
        self.posts = posts
        self.calls: list[tuple[str, str]] = []

    def fetch_posts(self, subreddit: str, sort: str) -> list[dict]:
        self.calls.append((subreddit, sort))
        if isinstance(self.posts, Exception):
            raise self.posts
        return self.posts


def test_telegram_channel_normalizes_text_caption_forwarded_and_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeTelegramClient(
        [
            {
                "message_id": 20,
                "chat": {"username": "philosophy"},
                "date": "2026-05-04T10:00:00Z",
                "text": "Post text https://example.com/a",
                "caption": "Media caption",
                "forwarded_message": {"text": "Forwarded context"},
                "author": "channel author",
            }
        ]
    )
    monkeypatch.setattr(
        telegram_module, "_create_telegram_client", lambda bot_token: client
    )
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="telegram_channel",
                    source_label="telegram",
                    credentials={"bot_token": "token"},
                    params={"channel_username": "@philosophy"},
                )
            ]
        )
    )

    first = manager.poll_once("telegram")
    second = manager.poll_once("telegram")

    assert first.errors == []
    assert len(first.items) == 1
    item = first.items[0]
    assert item.source == "telegram_channel"
    assert item.content == "Post text https://example.com/a\nMedia caption\nForwarded context"
    assert item.linked_urls == ["https://example.com/a"]
    assert item.author == "channel author"
    assert item.timestamp == datetime(2026, 5, 4, 10, tzinfo=timezone.utc)
    assert second.items == []
    assert client.calls == [
        {"channel_id": None, "channel_username": "@philosophy", "offset": None},
        {"channel_id": None, "channel_username": "@philosophy", "offset": 20},
    ]


def test_telegram_channel_reports_api_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingTelegramClient:
        def get_channel_messages(self, **kwargs: object) -> list[dict]:
            raise RuntimeError("telegram unavailable")

    monkeypatch.setattr(
        telegram_module,
        "_create_telegram_client",
        lambda bot_token: FailingTelegramClient(),
    )
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="telegram_channel",
                    source_label="telegram",
                    credentials={"bot_token": "token"},
                    params={"channel_id": "123"},
                )
            ]
        )
    )

    result = manager.poll_once("telegram")

    assert result.items == []
    assert result.errors[0].adapter_label == "telegram"
    assert result.errors[0].error == "telegram unavailable"


def test_reddit_adapter_normalizes_self_and_link_posts_and_sort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeRedditClient(
        [
            {
                "id": "old",
                "title": "Old link",
                "url": "https://example.com/old",
                "created_utc": 1_777_777_770,
                "author": "old_author",
                "is_self": False,
            },
            {
                "id": "new",
                "title": "New self",
                "selftext": "Self body https://example.com/in-body",
                "permalink": "/r/python/comments/new/new_self/",
                "created_utc": 1_777_777_780,
                "author": "new_author",
                "is_self": True,
            },
        ]
    )
    monkeypatch.setattr(
        reddit_module,
        "_create_reddit_client",
        lambda **kwargs: client,
    )
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="reddit",
                    source_label="reddit",
                    credentials={"client_id": "id", "client_secret": "secret"},
                    params={"subreddit": "python", "sort": "hot"},
                )
            ]
        )
    )

    first = manager.poll_once("reddit")
    second = manager.poll_once("reddit")

    assert first.errors == []
    assert [item.title for item in first.items] == ["Old link", "New self"]
    assert first.items[0].source == "reddit"
    assert first.items[0].url == "https://example.com/old"
    assert first.items[0].linked_urls == ["https://example.com/old"]
    assert first.items[1].content == "New self\nSelf body https://example.com/in-body"
    assert first.items[1].url == "https://www.reddit.com/r/python/comments/new/new_self/"
    assert first.items[1].linked_urls == [
        "https://www.reddit.com/r/python/comments/new/new_self/",
        "https://example.com/in-body",
    ]
    assert first.items[1].author == "new_author"
    assert first.items[1].timestamp == datetime.fromtimestamp(
        1_777_777_780, timezone.utc
    )
    assert second.items == []
    assert client.calls == [("python", "hot"), ("python", "hot")]


def test_reddit_adapter_reports_api_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reddit_module,
        "_create_reddit_client",
        lambda **kwargs: FakeRedditClient(RuntimeError("reddit unavailable")),
    )
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="reddit",
                    source_label="reddit",
                    credentials={"client_id": "id", "client_secret": "secret"},
                    params={"subreddit": "python", "sort": "new"},
                )
            ]
        )
    )

    result = manager.poll_once("reddit")

    assert result.items == []
    assert result.errors[0].adapter_label == "reddit"
    assert result.errors[0].url == "https://www.reddit.com/r/python/new.json?limit=25"
    assert result.errors[0].error == "reddit unavailable"
