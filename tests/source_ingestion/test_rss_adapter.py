from datetime import datetime, timezone

import pytest

from toolkit.source_ingestion import AdapterConfig, IngestionConfig, SourceIngestion


RSS_FEED = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Example Feed</title>
    <item>
      <guid>old</guid>
      <title>Old Entry</title>
      <link>https://example.com/old</link>
      <author>old@example.com</author>
      <pubDate>Fri, 01 May 2026 10:00:00 GMT</pubDate>
      <description><![CDATA[<p>Old body</p>]]></description>
    </item>
    <item>
      <guid>new</guid>
      <title>New Entry</title>
      <link>https://example.com/new</link>
      <author>new@example.com</author>
      <pubDate>Sat, 02 May 2026 11:00:00 GMT</pubDate>
      <content:encoded><![CDATA[
        <p>New <strong>body</strong> with https://example.com/in-body</p>
        <a href="https://example.com/linked">linked</a>
      ]]></content:encoded>
    </item>
  </channel>
</rss>
"""

ATOM_FEED = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:example.com,2026:1</id>
    <title>Atom Entry</title>
    <author><name>Atom Author</name></author>
    <link href="https://example.com/atom-entry" rel="alternate" />
    <updated>2026-05-03T12:00:00Z</updated>
    <content type="html">&lt;p&gt;Atom &lt;em&gt;body&lt;/em&gt;&lt;/p&gt;</content>
  </entry>
</feed>
"""


class FakeHeaders:
    def get_content_charset(self) -> str:
        return "utf-8"


class FakeResponse:
    headers = FakeHeaders()

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def _manager() -> SourceIngestion:
    return SourceIngestion(
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


def test_rss_adapter_normalizes_feed_entries_and_advances_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        seen["timeout"] = timeout
        return FakeResponse(RSS_FEED)

    monkeypatch.setattr("toolkit.source_ingestion.rss.urlopen", fake_urlopen)

    manager = _manager()
    first = manager.poll_once("feed")
    second = manager.poll_once("feed")

    assert first.errors == []
    assert seen["timeout"] == 30.0
    assert [item.title for item in first.items] == ["Old Entry", "New Entry"]
    assert first.items[1].content == "New body with https://example.com/in-body linked"
    assert first.items[1].source == "rss"
    assert first.items[1].timestamp == datetime(2026, 5, 2, 11, 0, tzinfo=timezone.utc)
    assert first.items[1].url == "https://example.com/new"
    assert first.items[1].author == "new@example.com"
    assert first.items[1].linked_urls == [
        "https://example.com/linked",
        "https://example.com/in-body",
    ]
    assert second.items == []
    assert second.errors == []


def test_atom_adapter_normalizes_namespaced_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "toolkit.source_ingestion.rss.urlopen",
        lambda request, timeout: FakeResponse(ATOM_FEED),
    )

    result = _manager().poll_once("feed")

    assert result.errors == []
    assert len(result.items) == 1
    assert result.items[0].title == "Atom Entry"
    assert result.items[0].author == "Atom Author"
    assert result.items[0].url == "https://example.com/atom-entry"
    assert result.items[0].content == "Atom body"
    assert result.items[0].timestamp == datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


def test_rss_adapter_reports_malformed_feed_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "toolkit.source_ingestion.rss.urlopen",
        lambda request, timeout: FakeResponse(b"<rss><channel>"),
    )

    result = _manager().poll_once("feed")

    assert result.items == []
    assert result.errors[0].adapter_label == "feed"
    assert result.errors[0].url == "https://example.com/feed.xml"
    assert "no element found" in result.errors[0].error


def test_disabled_rss_adapter_is_not_polled(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(request: object, timeout: float) -> object:
        raise AssertionError("disabled adapter should not fetch")

    monkeypatch.setattr("toolkit.source_ingestion.rss.urlopen", fail_if_called)
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="rss",
                    source_label="disabled",
                    enabled=False,
                    params={"feed_url": "https://example.com/feed.xml"},
                )
            ]
        )
    )

    assert manager.poll() == []
