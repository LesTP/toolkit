from dataclasses import fields
from datetime import datetime, timedelta

import toolkit.source_ingestion as source_ingestion
from toolkit.source_ingestion import (
    AdapterConfig,
    AdapterConfigError,
    AdapterNotFoundError,
    ContentItem,
    IngestionConfig,
    IngestionError,
    IngestionResult,
    SourceIngestion,
    SourceIngestionError,
)


def test_package_exports_arch_public_api() -> None:
    expected_exports = {
        "AdapterConfig",
        "AdapterConfigError",
        "AdapterNotFoundError",
        "ContentItem",
        "IngestionConfig",
        "IngestionError",
        "IngestionResult",
        "SourceIngestion",
        "SourceIngestionError",
    }

    assert set(source_ingestion.__all__) == expected_exports
    for exported_name in expected_exports:
        assert getattr(source_ingestion, exported_name) is not None


def test_arch_dataclass_field_names_match_contract() -> None:
    assert [field.name for field in fields(ContentItem)] == [
        "content",
        "source",
        "timestamp",
        "url",
        "linked_urls",
        "title",
        "author",
        "human_annotation",
    ]
    assert [field.name for field in fields(AdapterConfig)] == [
        "adapter_type",
        "source_label",
        "poll_interval",
        "enabled",
        "credentials",
        "params",
    ]
    assert [field.name for field in fields(IngestionConfig)] == [
        "adapters",
        "fetch_timeout",
        "max_content_length",
        "extract_links",
    ]
    assert [field.name for field in fields(IngestionResult)] == [
        "items",
        "adapter_label",
        "errors",
        "poll_timestamp",
    ]
    assert [field.name for field in fields(IngestionError)] == [
        "url",
        "error",
        "adapter_label",
    ]


def test_arch_dataclasses_construct_with_expected_defaults() -> None:
    timestamp = datetime(2026, 1, 1)
    item = ContentItem(content="text", source="rss", timestamp=timestamp)
    adapter = AdapterConfig(adapter_type="rss", source_label="feed")
    config = IngestionConfig(adapters=[adapter])
    error = IngestionError(url=None, error="bad item", adapter_label="feed")
    result = IngestionResult(
        items=[item],
        adapter_label="feed",
        errors=[error],
        poll_timestamp=timestamp,
    )

    assert item.url is None
    assert item.linked_urls == []
    assert item.title is None
    assert item.author is None
    assert item.human_annotation is None
    assert adapter.poll_interval == timedelta(hours=4)
    assert adapter.enabled is True
    assert adapter.credentials is None
    assert adapter.params == {}
    assert config.fetch_timeout == timedelta(seconds=30)
    assert config.max_content_length == 50_000
    assert config.extract_links is True
    assert result.errors == [error]
    manager_config = IngestionConfig(
        adapters=[
            AdapterConfig(
                adapter_type="rss",
                source_label="feed",
                params={"feed_url": "https://example.com/feed.xml"},
            )
        ]
    )
    assert isinstance(SourceIngestion(manager_config), SourceIngestion)
    assert issubclass(AdapterConfigError, SourceIngestionError)
    assert issubclass(AdapterNotFoundError, SourceIngestionError)
