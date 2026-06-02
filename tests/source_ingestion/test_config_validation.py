from datetime import timedelta

import pytest

from toolkit.source_ingestion import (
    AdapterConfig,
    AdapterConfigError,
    AdapterNotFoundError,
    IngestionConfig,
    SourceIngestion,
)


def _config(*adapters: AdapterConfig) -> IngestionConfig:
    return IngestionConfig(adapters=list(adapters))


def test_source_ingestion_accepts_valid_arch_adapter_configs() -> None:
    manager = SourceIngestion(
        _config(
            AdapterConfig(
                adapter_type="telegram_channel",
                source_label="telegram",
                credentials={"bot_token": "token"},
                params={"channel_username": "@channel"},
            ),
            AdapterConfig(
                adapter_type="rss",
                source_label="feed",
                params={"feed_url": "https://example.com/feed.xml"},
            ),
            AdapterConfig(
                adapter_type="reddit",
                source_label="subreddit",
                credentials={"client_id": "id", "client_secret": "secret"},
                params={"subreddit": "python", "sort": "new"},
            ),
            AdapterConfig(
                adapter_type="human_share",
                source_label="shares",
                poll_interval=timedelta(minutes=5),
                credentials={"bot_token": "token"},
                params={"bot_chat_id": "12345"},
            ),
            AdapterConfig(
                adapter_type="corpus_blog",
                source_label="blog",
                params={"archive_path": "/archive", "format": "markdown"},
            ),
            AdapterConfig(
                adapter_type="corpus_conversations",
                source_label="chats",
                params={"archive_path": "/archive", "format": "json"},
            ),
            AdapterConfig(
                adapter_type="corpus_text",
                source_label="notes",
                params={"archive_path": "/archive"},
            ),
        )
    )

    assert manager._get_adapter_config("feed").adapter_type == "rss"


def test_source_ingestion_accepts_telegram_channel_id_alternative() -> None:
    manager = SourceIngestion(
        _config(
            AdapterConfig(
                adapter_type="telegram_channel",
                source_label="telegram",
                credentials={"bot_token": "token"},
                params={"channel_id": "12345"},
            )
        )
    )

    assert manager._get_adapter_config("telegram").params == {"channel_id": "12345"}


def test_source_ingestion_rejects_unknown_adapter_type() -> None:
    with pytest.raises(AdapterConfigError, match="unknown adapter_type"):
        SourceIngestion(
            _config(AdapterConfig(adapter_type="webhook", source_label="unknown"))
        )


def test_source_ingestion_rejects_empty_source_label() -> None:
    with pytest.raises(AdapterConfigError, match="source_label is required"):
        SourceIngestion(
            _config(
                AdapterConfig(
                    adapter_type="rss",
                    source_label="",
                    params={"feed_url": "https://example.com/feed.xml"},
                )
            )
        )


def test_source_ingestion_rejects_duplicate_source_labels() -> None:
    with pytest.raises(AdapterConfigError, match="duplicate adapter source_label"):
        SourceIngestion(
            _config(
                AdapterConfig(
                    adapter_type="rss",
                    source_label="same",
                    params={"feed_url": "https://example.com/a.xml"},
                ),
                AdapterConfig(
                    adapter_type="rss",
                    source_label="same",
                    params={"feed_url": "https://example.com/b.xml"},
                ),
            )
        )


@pytest.mark.parametrize(
    ("adapter", "message"),
    [
        (
            AdapterConfig(adapter_type="rss", source_label="feed"),
            "rss adapter missing required params",
        ),
        (
            AdapterConfig(
                adapter_type="telegram_channel",
                source_label="telegram",
                credentials={"bot_token": "token"},
            ),
            "telegram_channel adapter missing required params",
        ),
        (
            AdapterConfig(
                adapter_type="telegram_channel",
                source_label="telegram",
                params={"channel_id": "123"},
            ),
            "telegram_channel adapter missing required credentials",
        ),
        (
            AdapterConfig(
                adapter_type="reddit",
                source_label="subreddit",
                credentials={"client_id": "id"},
                params={"subreddit": "python", "sort": "new"},
            ),
            "reddit adapter missing required credentials",
        ),
        (
            AdapterConfig(
                adapter_type="human_share",
                source_label="shares",
                credentials={"bot_token": "token"},
            ),
            "human_share adapter missing required params",
        ),
        (
            AdapterConfig(adapter_type="corpus_text", source_label="text"),
            "corpus_text adapter missing required params",
        ),
    ],
)
def test_source_ingestion_rejects_missing_required_fields(
    adapter: AdapterConfig, message: str
) -> None:
    with pytest.raises(AdapterConfigError, match=message):
        SourceIngestion(_config(adapter))


@pytest.mark.parametrize(
    "adapter",
    [
        AdapterConfig(
            adapter_type="reddit",
            source_label="subreddit",
            credentials={"client_id": "id", "client_secret": "secret"},
            params={"subreddit": "python", "sort": "rising"},
        ),
        AdapterConfig(
            adapter_type="corpus_blog",
            source_label="blog",
            params={"archive_path": "/archive", "format": "json"},
        ),
        AdapterConfig(
            adapter_type="corpus_conversations",
            source_label="chats",
            params={"archive_path": "/archive", "format": "markdown"},
        ),
    ],
)
def test_source_ingestion_rejects_invalid_enum_params(adapter: AdapterConfig) -> None:
    with pytest.raises(AdapterConfigError):
        SourceIngestion(_config(adapter))


def test_poll_all_filters_disabled_adapters() -> None:
    manager = SourceIngestion(
        _config(
            AdapterConfig(
                adapter_type="rss",
                source_label="disabled",
                enabled=False,
                params={"feed_url": "https://example.com/feed.xml"},
            )
        )
    )

    assert manager.poll() == []


def test_poll_all_with_no_adapters_returns_empty_results() -> None:
    manager = SourceIngestion(_config())

    assert manager.poll() == []


def test_poll_specific_unknown_adapter_raises_adapter_not_found() -> None:
    manager = SourceIngestion(_config())

    with pytest.raises(AdapterNotFoundError, match="missing"):
        manager.poll("missing")


def test_poll_once_unknown_adapter_raises_adapter_not_found() -> None:
    manager = SourceIngestion(_config())

    with pytest.raises(AdapterNotFoundError, match="missing"):
        manager.poll_once("missing")
