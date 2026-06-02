from datetime import datetime, timezone
import os

import pytest

import toolkit.source_ingestion.corpus as corpus_module
from toolkit.source_ingestion import AdapterConfig, IngestionConfig, SourceIngestion
from toolkit.source_ingestion.normalization import PageFetchResult


def test_corpus_text_imports_plain_text_paragraphs_and_advances_marker(tmp_path) -> None:
    corpus_file = tmp_path / "notes.txt"
    corpus_file.write_text(
        "First paragraph with https://example.com/a\n\nSecond paragraph", encoding="utf-8"
    )
    os.utime(corpus_file, (1_777_777_777, 1_777_777_777))

    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="corpus_text",
                    source_label="notes",
                    params={"archive_path": str(corpus_file)},
                )
            ]
        )
    )

    first = manager.poll_once("notes")
    second = manager.poll_once("notes")

    assert first.errors == []
    assert [item.content for item in first.items] == [
        "First paragraph with https://example.com/a",
        "Second paragraph",
    ]
    assert {item.source for item in first.items} == {"corpus_text"}
    assert first.items[0].title == "notes"
    assert first.items[0].url == str(corpus_file)
    assert first.items[0].linked_urls == ["https://example.com/a"]
    assert first.items[0].timestamp == datetime.fromtimestamp(
        1_777_777_777, timezone.utc
    )
    assert second.items == []
    assert second.errors == []


def test_corpus_text_imports_recursive_directory_in_stable_order(tmp_path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("B", encoding="utf-8")
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    (tmp_path / "ignored.md").write_text("ignored", encoding="utf-8")

    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="corpus_text",
                    source_label="notes",
                    params={"archive_path": str(tmp_path)},
                )
            ]
        )
    )

    result = manager.poll_once("notes")

    assert [item.content for item in result.items] == ["A", "B"]
    assert result.errors == []


def test_corpus_blog_imports_markdown_frontmatter_metadata(tmp_path) -> None:
    post = tmp_path / "post.md"
    post.write_text(
        """---
title: Exact Post Title
date: 2026-05-01T10:30:00Z
author: Writer
---

Intro paragraph.

Second [link](https://example.com/post).
""",
        encoding="utf-8",
    )

    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="corpus_blog",
                    source_label="blog",
                    params={"archive_path": str(tmp_path), "format": "markdown"},
                )
            ]
        )
    )

    result = manager.poll_once("blog")

    assert result.errors == []
    assert [item.content for item in result.items] == [
        "Intro paragraph.",
        "Second link https://example.com/post.",
    ]
    assert result.items[0].source == "corpus_blog"
    assert result.items[0].title == "Exact Post Title"
    assert result.items[0].author == "Writer"
    assert result.items[0].timestamp == datetime(2026, 5, 1, 10, 30, tzinfo=timezone.utc)
    assert result.items[1].linked_urls == ["https://example.com/post"]


def test_corpus_blog_imports_html_title_date_and_links(tmp_path) -> None:
    post = tmp_path / "post.html"
    post.write_text(
        """
        <html>
          <head>
            <title>HTML Post</title>
            <meta name="date" content="2026-05-02T12:00:00Z">
          </head>
          <body>
            <p>First HTML paragraph.</p>
            <p>Second <a href="https://example.com/html">HTML link</a>.</p>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="corpus_blog",
                    source_label="blog",
                    params={"archive_path": str(post), "format": "html"},
                )
            ]
        )
    )

    result = manager.poll_once("blog")

    assert result.errors == []
    assert result.items[0].title == "HTML Post"
    assert result.items[0].timestamp == datetime(2026, 5, 2, 12, tzinfo=timezone.utc)
    assert result.items[0].content == "First HTML paragraph. Second HTML link ."
    assert result.items[0].linked_urls == ["https://example.com/html"]


def test_corpus_adapter_reports_invalid_path_without_raising(tmp_path) -> None:
    missing = tmp_path / "missing"
    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="corpus_text",
                    source_label="notes",
                    params={"archive_path": str(missing)},
                )
            ]
        )
    )

    result = manager.poll_once("notes")

    assert result.items == []
    assert result.errors[0].adapter_label == "notes"
    assert result.errors[0].url == str(missing)
    assert "archive path not found" in result.errors[0].error


def test_corpus_adapter_applies_max_content_truncation(tmp_path) -> None:
    corpus_file = tmp_path / "long.txt"
    corpus_file.write_text("abcdef https://example.com/full", encoding="utf-8")

    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="corpus_text",
                    source_label="notes",
                    params={"archive_path": str(corpus_file)},
                )
            ],
            max_content_length=6,
        )
    )

    result = manager.poll_once("notes")

    assert result.items[0].content == "abcdef"
    assert result.items[0].linked_urls == ["https://example.com/full"]


def test_corpus_livejournal_imports_html_export_metadata(tmp_path) -> None:
    post = tmp_path / "entry.html"
    post.write_text(
        """
        <html>
          <head><title>Private Entry</title></head>
          <body>
            <time datetime="2024-04-05T09:15:00Z">April 5</time>
            <article><p>A reflective paragraph.</p></article>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="corpus_livejournal",
                    source_label="lj",
                    params={"archive_path": str(tmp_path)},
                )
            ]
        )
    )

    result = manager.poll_once("lj")

    assert result.errors == []
    assert len(result.items) == 1
    assert result.items[0].source == "corpus_livejournal"
    assert result.items[0].title == "Private Entry"
    assert result.items[0].timestamp == datetime(2024, 4, 5, 9, 15, tzinfo=timezone.utc)
    assert "A reflective paragraph." in result.items[0].content


def test_corpus_twitter_fetches_linked_content_and_preserves_annotation(
    tmp_path, monkeypatch
) -> None:
    archive = tmp_path / "tweets.js"
    archive.write_text(
        """
        window.YTD.tweets.part0 = [
          {"tweet": {
            "id_str": "1",
            "created_at": "Fri May 01 10:30:00 +0000 2026",
            "full_text": "Worth reading https://t.co/a",
            "entities": {"urls": [
              {"url": "https://t.co/a", "expanded_url": "https://example.com/article"}
            ]},
            "user": {"screen_name": "writer"}
          }}
        ]
        """,
        encoding="utf-8",
    )

    def fake_fetch(url: str, timeout_seconds: float):
        assert url == "https://example.com/article"
        assert timeout_seconds == 30
        return PageFetchResult(
            url=url,
            text="Fetched article body",
            title="Fetched Title",
            linked_urls=["https://example.com/next"],
        )

    monkeypatch.setattr(corpus_module, "fetch_url_text", fake_fetch)

    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="corpus_twitter",
                    source_label="twitter",
                    params={"archive_path": str(archive)},
                )
            ]
        )
    )

    result = manager.poll_once("twitter")

    assert result.errors == []
    assert len(result.items) == 1
    item = result.items[0]
    assert item.source == "corpus_twitter"
    assert item.content == "Fetched article body"
    assert item.url == "https://example.com/article"
    assert item.linked_urls == [
        "https://example.com/article",
        "https://example.com/next",
    ]
    assert item.title == "Fetched Title"
    assert item.author == "writer"
    assert item.human_annotation == "Worth reading"
    assert item.timestamp == datetime(2026, 5, 1, 10, 30, tzinfo=timezone.utc)


def test_corpus_twitter_retweet_and_failed_link_fallback(tmp_path, monkeypatch) -> None:
    archive = tmp_path / "tweets.json"
    archive.write_text(
        """
        [
          {
            "id_str": "1",
            "created_at": "2026-05-01T10:00:00Z",
            "full_text": "Interesting context https://example.com/missing",
            "entities": {"urls": [
              {"expanded_url": "https://example.com/missing"}
            ]}
          },
          {
            "id_str": "2",
            "created_at": "2026-05-02T10:00:00Z",
            "full_text": "RT @source: Original thought",
            "retweeted_status": {"id_str": "original"}
          }
        ]
        """,
        encoding="utf-8",
    )

    def failing_fetch(url: str, timeout_seconds: float):
        raise OSError("network unavailable")

    monkeypatch.setattr(corpus_module, "fetch_url_text", failing_fetch)

    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="corpus_twitter",
                    source_label="twitter",
                    params={"archive_path": str(archive)},
                )
            ]
        )
    )

    result = manager.poll_once("twitter")

    assert [item.content for item in result.items] == [
        "Interesting context",
        "RT @source: Original thought",
    ]
    assert result.items[0].human_annotation == "Interesting context"
    assert result.items[0].url == "https://example.com/missing"
    assert result.items[1].title == "Retweet 2"
    assert result.items[1].human_annotation is None
    assert len(result.errors) == 1
    assert result.errors[0].url == "https://example.com/missing"
    assert "network unavailable" in result.errors[0].error


def test_corpus_conversations_imports_json_messages_with_metadata(tmp_path) -> None:
    archive = tmp_path / "conversation.json"
    archive.write_text(
        """
        {
          "title": "Architecture Chat",
          "messages": [
            {
              "role": "user",
              "content": "I care about boundaries.",
              "timestamp": "2026-05-01T11:00:00Z"
            },
            {
              "role": "assistant",
              "content": [{"text": "Then keep adapters leaf-local."}],
              "timestamp": "2026-05-01T11:01:00Z"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="corpus_conversations",
                    source_label="chats",
                    params={"archive_path": str(tmp_path), "format": "json"},
                )
            ]
        )
    )

    result = manager.poll_once("chats")

    assert result.errors == []
    assert [item.content for item in result.items] == [
        "I care about boundaries.",
        "Then keep adapters leaf-local.",
    ]
    assert {item.title for item in result.items} == {"Architecture Chat"}
    assert [item.author for item in result.items] == ["user", "assistant"]
    assert result.items[0].source == "corpus_conversations"
    assert result.items[0].timestamp == datetime(2026, 5, 1, 11, tzinfo=timezone.utc)


@pytest.mark.parametrize("file_format", ["json", "text"])
def test_corpus_conversations_advances_marker(tmp_path, file_format) -> None:
    archive = tmp_path / f"conversation.{file_format}"
    if file_format == "json":
        archive.write_text(
            '[{"title": "Chat", "messages": [{"content": "One"}]}]',
            encoding="utf-8",
        )
    else:
        archive.write_text("One\n\nTwo", encoding="utf-8")

    manager = SourceIngestion(
        IngestionConfig(
            adapters=[
                AdapterConfig(
                    adapter_type="corpus_conversations",
                    source_label="chats",
                    params={"archive_path": str(tmp_path), "format": file_format},
                )
            ]
        )
    )

    first = manager.poll_once("chats")
    second = manager.poll_once("chats")

    assert first.items
    assert second.items == []
    assert second.errors == []
