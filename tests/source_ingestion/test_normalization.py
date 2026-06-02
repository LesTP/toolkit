from datetime import datetime, timezone
from urllib.error import URLError

import pytest

from toolkit.source_ingestion.normalization import (
    build_content_item,
    extract_urls,
    fetch_url_text,
    html_to_text,
    is_marker_newer,
    marker_sort_key,
    truncate_content,
)
from toolkit.source_ingestion.types import IngestionConfig


def test_extract_urls_preserves_order_and_deduplicates() -> None:
    text = (
        "See https://example.com/a, then https://example.com/b?q=1. "
        "Again: https://example.com/a"
    )

    assert extract_urls(text) == [
        "https://example.com/a",
        "https://example.com/b?q=1",
    ]


def test_extract_urls_ignores_empty_text() -> None:
    assert extract_urls(None) == []
    assert extract_urls("") == []


def test_truncate_content_applies_configured_character_limit() -> None:
    assert truncate_content("abcdef", 4) == "abcd"
    assert truncate_content("abcdef", 6) == "abcdef"
    assert truncate_content("abcdef", 0) == ""


def test_truncate_content_rejects_negative_limit() -> None:
    with pytest.raises(ValueError, match="max_content_length"):
        truncate_content("abcdef", -1)


def test_build_content_item_truncates_content_and_preserves_metadata() -> None:
    timestamp = datetime(2026, 1, 2, 3, 4, 5)

    item = build_content_item(
        content="abcdef https://example.com/content",
        source="human_share",
        timestamp=timestamp,
        config=IngestionConfig(adapters=[], max_content_length=6),
        url="https://example.com/source",
        linked_urls=["https://example.com/source"],
        title="Title",
        author="Author",
        human_annotation="note https://example.com/annotation",
    )

    assert item.content == "abcdef"
    assert item.source == "human_share"
    assert item.timestamp is timestamp
    assert item.url == "https://example.com/source"
    assert item.linked_urls == [
        "https://example.com/source",
        "https://example.com/content",
        "https://example.com/annotation",
    ]
    assert item.title == "Title"
    assert item.author == "Author"
    assert item.human_annotation == "note https://example.com/annotation"


def test_build_content_item_can_disable_link_extraction() -> None:
    item = build_content_item(
        content="https://example.com/content",
        source="rss",
        timestamp=datetime(2026, 1, 1),
        config=IngestionConfig(adapters=[], extract_links=False),
        linked_urls=["https://example.com/explicit"],
    )

    assert item.linked_urls == ["https://example.com/explicit"]


def test_build_content_item_deduplicates_explicit_and_extracted_links() -> None:
    item = build_content_item(
        content="Read https://example.com/a and https://example.com/b",
        source="rss",
        timestamp=datetime(2026, 1, 1),
        config=IngestionConfig(adapters=[]),
        linked_urls=["https://example.com/b", "https://example.com/a"],
        human_annotation="same https://example.com/a",
    )

    assert item.linked_urls == [
        "https://example.com/b",
        "https://example.com/a",
    ]


def test_build_content_item_preserves_links_from_truncated_content() -> None:
    item = build_content_item(
        content="prefix https://example.com/kept-after-truncation",
        source="rss",
        timestamp=datetime(2026, 1, 1),
        config=IngestionConfig(adapters=[], max_content_length=6),
    )

    assert item.content == "prefix"
    assert item.linked_urls == ["https://example.com/kept-after-truncation"]


def test_html_to_text_extracts_readable_text_title_and_links() -> None:
    result = html_to_text(
        """
        <html>
          <head><title>Example &amp; Title</title><style>.x {}</style></head>
          <body>
            <h1>Hello</h1>
            <script>ignored()</script>
            <p>Read <a href="https://example.com/a">A</a></p>
            <a href="/relative">relative</a>
          </body>
        </html>
        """
    )

    assert result.text == "Hello Read A relative"
    assert result.title == "Example & Title"
    assert result.linked_urls == ["https://example.com/a"]


def test_fetch_url_text_uses_fetch_abstraction_and_extracts_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeHeaders:
        def get_content_charset(self) -> str:
            return "utf-8"

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"<title>T</title><p>Body https://example.com/body</p>"

    seen: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        seen["request"] = request
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("toolkit.source_ingestion.normalization.urlopen", fake_urlopen)

    result = fetch_url_text("https://example.com/page", timeout_seconds=2.5)

    assert seen["timeout"] == 2.5
    assert result.url == "https://example.com/page"
    assert result.text == "Body https://example.com/body"
    assert result.title == "T"
    assert result.linked_urls == ["https://example.com/body"]


def test_fetch_url_text_propagates_url_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: float) -> object:
        raise URLError("network down")

    monkeypatch.setattr("toolkit.source_ingestion.normalization.urlopen", fake_urlopen)

    with pytest.raises(URLError, match="network down"):
        fetch_url_text("https://example.com/page", timeout_seconds=2.5)


def test_marker_ordering_handles_none_numbers_datetimes_and_strings() -> None:
    early = datetime(2026, 1, 1, tzinfo=timezone.utc)
    late = datetime(2026, 1, 2, tzinfo=timezone.utc)

    assert is_marker_newer(1, None) is True
    assert is_marker_newer(2, 1) is True
    assert is_marker_newer(1, 2) is False
    assert is_marker_newer(late, early) is True
    assert is_marker_newer("b", "a") is True
    assert marker_sort_key(None) < marker_sort_key(0)
