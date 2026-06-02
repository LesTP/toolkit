import json
from datetime import datetime, timezone

import pytest

from toolkit.source_ingestion import (
    AdapterConfig,
    ContentItem,
    IngestionConfig,
    SourceIngestion,
)
from toolkit.source_ingestion.adapters import (
    AdapterItemError,
    AdapterRegistry,
    AdapterPollResult,
    LastSeenMarker,
    adapter_error_from_exception,
)
from toolkit.source_ingestion.ingestion import _ADAPTER_REGISTRY, _build_adapter_registry


class FakeAdapter:
    def __init__(self, result: AdapterPollResult) -> None:
        self.result = result
        self.seen_markers: list[LastSeenMarker] = []

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        self.seen_markers.append(last_seen_marker)
        return self.result


class FailingAdapter:
    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        raise RuntimeError("adapter broke")


@pytest.fixture
def fake_registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, FakeAdapter]:
    adapters: dict[str, FakeAdapter] = {}

    def factory(config: AdapterConfig) -> FakeAdapter:
        adapter = FakeAdapter(
            AdapterPollResult(
                items=[
                    ContentItem(
                        content=f"{config.source_label} item",
                        source=config.adapter_type,
                        timestamp=datetime(2026, 1, 1),
                    )
                ],
                errors=[AdapterItemError(error="bad item", url="https://example.com/bad")],
                next_marker=f"{config.source_label}:marker",
            )
        )
        adapters[config.source_label] = adapter
        return adapter

    monkeypatch.setitem(_ADAPTER_REGISTRY, "fake_source", factory)
    return adapters


def test_poll_once_assembles_result_and_tracks_last_seen_marker(
    fake_registry: dict[str, FakeAdapter],
) -> None:
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(adapter_type="fake_source", source_label="fake"),
            ]
        )
    )

    first = manager.poll_once("fake")
    second = manager.poll_once("fake")

    assert first.adapter_label == "fake"
    assert [item.content for item in first.items] == ["fake item"]
    assert first.errors[0].adapter_label == "fake"
    assert first.errors[0].url == "https://example.com/bad"
    assert first.errors[0].error == "bad item"
    assert fake_registry["fake"].seen_markers == [None, "fake:marker"]
    assert second.poll_timestamp >= first.poll_timestamp


def test_poll_all_uses_enabled_adapters_in_config_order(
    fake_registry: dict[str, FakeAdapter],
) -> None:
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(adapter_type="fake_source", source_label="first"),
                AdapterConfig(
                    adapter_type="fake_source",
                    source_label="disabled",
                    enabled=False,
                ),
                AdapterConfig(adapter_type="fake_source", source_label="second"),
            ]
        )
    )

    results = manager.poll()

    assert [result.adapter_label for result in results] == ["first", "second"]
    assert "disabled" in fake_registry
    assert fake_registry["disabled"].seen_markers == []


def test_poll_once_can_poll_disabled_adapter_by_explicit_label(
    fake_registry: dict[str, FakeAdapter],
) -> None:
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="fake_source",
                    source_label="disabled",
                    enabled=False,
                ),
            ]
        )
    )

    result = manager.poll_once("disabled")

    assert result.adapter_label == "disabled"
    assert [item.content for item in result.items] == ["disabled item"]
    assert fake_registry["disabled"].seen_markers == [None]


def test_poll_specific_adapter_wraps_adapter_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(_ADAPTER_REGISTRY, "failing_source", lambda config: FailingAdapter())
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(adapter_type="failing_source", source_label="failing"),
            ]
        )
    )

    result = manager.poll("failing")[0]

    assert result.items == []
    assert result.adapter_label == "failing"
    assert result.errors[0].adapter_label == "failing"
    assert result.errors[0].url is None
    assert result.errors[0].error == "adapter broke"


def test_rss_adapter_fetch_error_is_reported_in_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(request: object, timeout: float) -> object:
        raise OSError("network down")

    monkeypatch.setattr("toolkit.source_ingestion.rss.urlopen", failing_urlopen)
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="rss",
                    source_label="feed",
                    params={"feed_url": "https://example.com/feed.xml"},
                )
            ]
        )
    )

    result = manager.poll_once("feed")

    assert result.items == []
    assert result.adapter_label == "feed"
    assert result.errors[0].adapter_label == "feed"
    assert result.errors[0].url == "https://example.com/feed.xml"
    assert result.errors[0].error == "network down"


def test_private_registry_builds_with_concrete_factory_override() -> None:
    def factory(config: AdapterConfig) -> FakeAdapter:
        return FakeAdapter(
            AdapterPollResult(
                items=[
                    ContentItem(
                        content=config.source_label,
                        source=config.adapter_type,
                        timestamp=datetime(2026, 1, 1),
                    )
                ],
                next_marker=1,
            )
        )

    registry = _build_adapter_registry({"rss": factory})
    adapter = registry.create(
        AdapterConfig(
            adapter_type="rss",
            source_label="feed",
            params={"feed_url": "https://example.com/feed.xml"},
        )
    )

    assert adapter.poll(None).items[0].content == "feed"


def test_private_registry_rejects_invalid_factory() -> None:
    with pytest.raises(TypeError, match="must be callable"):
        AdapterRegistry({"rss": None})  # type: ignore[arg-type]


def test_adapter_error_from_exception_preserves_url_context() -> None:
    error = adapter_error_from_exception(
        RuntimeError("bad fetch"), url="https://example.com/bad"
    )

    assert error.error == "bad fetch"
    assert error.url == "https://example.com/bad"


def test_marker_store_persists_last_seen_across_manager_instances(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    adapters: dict[str, FakeAdapter] = {}

    def factory(config: AdapterConfig) -> FakeAdapter:
        adapter = FakeAdapter(
            AdapterPollResult(
                items=[
                    ContentItem(
                        content=config.source_label,
                        source=config.adapter_type,
                        timestamp=datetime(2026, 1, 1),
                    )
                ],
                next_marker=f"{config.source_label}:marker",
            )
        )
        adapters[config.source_label] = adapter
        return adapter

    monkeypatch.setitem(_ADAPTER_REGISTRY, "durable_source", factory)
    marker_path = tmp_path / "source_ingestion_markers.json"
    config = IngestionConfig(
        adapters=[
            AdapterConfig(
                adapter_type="durable_source",
                source_label="feed",
                params={"marker_store_path": str(marker_path)},
            ),
        ]
    )

    SourceIngestion(config).poll_once("feed")
    SourceIngestion(config).poll_once("feed")

    assert adapters["feed"].seen_markers == ["feed:marker"]
    assert json.loads(marker_path.read_text(encoding="utf-8")) == {
        "markers": {
            "feed": {"type": "str", "value": "feed:marker"},
        }
    }


def test_marker_store_preserves_per_adapter_markers_for_mixed_poll(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    adapters: dict[str, FakeAdapter] = {}

    def factory(config: AdapterConfig) -> FakeAdapter:
        adapter = FakeAdapter(
            AdapterPollResult(
                items=[
                    ContentItem(
                        content=config.source_label,
                        source=config.adapter_type,
                        timestamp=datetime(2026, 1, 1),
                    )
                ],
                next_marker=f"{config.source_label}:marker",
            )
        )
        adapters[config.source_label] = adapter
        return adapter

    monkeypatch.setitem(_ADAPTER_REGISTRY, "mixed_source", factory)
    marker_path = tmp_path / "mixed_markers.json"
    config = IngestionConfig(
        adapters=[
            AdapterConfig(
                adapter_type="mixed_source",
                source_label="rss",
                params={"marker_store_path": str(marker_path)},
            ),
            AdapterConfig(
                adapter_type="mixed_source",
                source_label="human",
                params={"marker_store_path": str(marker_path)},
            ),
        ]
    )

    first_results = SourceIngestion(config).poll()
    SourceIngestion(config).poll()

    assert [result.adapter_label for result in first_results] == ["rss", "human"]
    assert adapters["rss"].seen_markers == ["rss:marker"]
    assert adapters["human"].seen_markers == ["human:marker"]
    assert json.loads(marker_path.read_text(encoding="utf-8")) == {
        "markers": {
            "human": {"type": "str", "value": "human:marker"},
            "rss": {"type": "str", "value": "rss:marker"},
        }
    }


def test_marker_store_preserves_marker_types(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    marker = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    adapter = FakeAdapter(AdapterPollResult(next_marker=marker))
    monkeypatch.setitem(_ADAPTER_REGISTRY, "datetime_source", lambda config: adapter)
    marker_path = tmp_path / "markers.json"

    SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="datetime_source",
                    source_label="archive",
                    params={"marker_store_path": str(marker_path)},
                ),
            ]
        )
    ).poll_once("archive")

    restored_adapter = FakeAdapter(AdapterPollResult(next_marker=marker))
    monkeypatch.setitem(
        _ADAPTER_REGISTRY, "datetime_source", lambda config: restored_adapter
    )
    SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="datetime_source",
                    source_label="archive",
                    params={"marker_store_path": str(marker_path)},
                ),
            ]
        )
    ).poll_once("archive")

    assert restored_adapter.seen_markers == [marker]
