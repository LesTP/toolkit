"""Shared content normalization helpers for source adapters."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from toolkit.source_ingestion.types import ContentItem, IngestionConfig

_URL_RE = re.compile(r"https?://[^\s<>'\"]+")
_TRAILING_URL_PUNCTUATION = ".,;:!?)]}"


@dataclass
class PageFetchResult:
    url: str
    text: str
    title: str | None = None
    linked_urls: list[str] | None = None


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._links: list[str] = []
        self._title_chunks: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if href and href.startswith(("http://", "https://")):
                self._links.append(href)
        if tag in {"br", "p", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
            return
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title_chunks.append(data)
        else:
            self._chunks.append(data)

    @property
    def text(self) -> str:
        return _collapse_text(" ".join(self._chunks))

    @property
    def title(self) -> str | None:
        title = _collapse_text(" ".join(self._title_chunks))
        return title or None

    @property
    def linked_urls(self) -> list[str]:
        return _dedupe_preserving_order(self._links)


def extract_urls(text: str | None) -> list[str]:
    """Extract HTTP(S) URLs from text, preserving first-seen order."""

    if not text:
        return []

    urls: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(_TRAILING_URL_PUNCTUATION)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def html_to_text(html: str) -> PageFetchResult:
    """Extract readable text, title, and absolute HTTP(S) links from HTML."""

    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    return PageFetchResult(
        url="",
        text=extractor.text,
        title=extractor.title,
        linked_urls=extractor.linked_urls,
    )


def fetch_url_text(url: str, timeout_seconds: float) -> PageFetchResult:
    """Fetch a URL with stdlib HTTP and return extracted page text."""

    request = Request(url, headers={"User-Agent": "phosphene-source-ingestion/0.1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
            content_type = response.headers.get_content_charset() or "utf-8"
    except URLError:
        raise

    body = raw.decode(content_type, errors="replace")
    result = html_to_text(body)
    result.url = url
    result.linked_urls = _dedupe_preserving_order(
        [*(result.linked_urls or []), *extract_urls(body)]
    )
    return result


def marker_sort_key(marker: str | int | float | datetime | None) -> tuple[int, float | str]:
    """Return a deterministic ordering key for last-seen markers."""

    if marker is None:
        return (0, 0.0)
    if isinstance(marker, datetime):
        return (1, marker.timestamp())
    if isinstance(marker, bool):
        return (2, int(marker))
    if isinstance(marker, int | float):
        return (2, float(marker))
    return (3, str(marker))


def is_marker_newer(
    marker: str | int | float | datetime | None,
    last_seen_marker: str | int | float | datetime | None,
) -> bool:
    return marker_sort_key(marker) > marker_sort_key(last_seen_marker)


def truncate_content(content: str, max_content_length: int) -> str:
    if max_content_length < 0:
        raise ValueError("max_content_length must be non-negative")
    return content[:max_content_length]


def build_content_item(
    *,
    content: str,
    source: str,
    timestamp: datetime,
    config: IngestionConfig,
    url: str | None = None,
    linked_urls: Iterable[str] | None = None,
    title: str | None = None,
    author: str | None = None,
    human_annotation: str | None = None,
) -> ContentItem:
    """Assemble a normalized ContentItem without fetching external content."""

    normalized_links = list(linked_urls or [])
    if config.extract_links:
        normalized_links.extend(extract_urls(content))
        normalized_links.extend(extract_urls(human_annotation))

    deduped_links: list[str] = []
    seen: set[str] = set()
    for linked_url in normalized_links:
        if linked_url not in seen:
            seen.add(linked_url)
            deduped_links.append(linked_url)

    return ContentItem(
        content=truncate_content(content, config.max_content_length),
        source=source,
        timestamp=timestamp,
        url=url,
        linked_urls=deduped_links,
        title=title,
        author=author,
        human_annotation=human_annotation,
    )


def _collapse_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _dedupe_preserving_order(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
