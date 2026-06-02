"""RSS and Atom source adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from toolkit.source_ingestion.adapters import (
    AdapterItemError,
    AdapterPollResult,
    LastSeenMarker,
)
from toolkit.source_ingestion.normalization import (
    build_content_item,
    html_to_text,
    is_marker_newer,
)
from toolkit.source_ingestion.types import AdapterConfig, ContentItem, IngestionConfig

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}"
_DC_NS = "{http://purl.org/dc/elements/1.1/}"


@dataclass
class _FeedEntry:
    marker: str
    timestamp: datetime
    content: str
    url: str | None = None
    title: str | None = None
    author: str | None = None
    linked_urls: list[str] | None = None


class RssAdapter:
    """Poll an RSS or Atom feed and normalize new entries."""

    def __init__(self, config: AdapterConfig, ingestion_config: IngestionConfig) -> None:
        self.config = config
        self.ingestion_config = ingestion_config
        self.feed_url = str(config.params["feed_url"])

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        try:
            feed_xml = _fetch_feed_xml(
                self.feed_url, self.ingestion_config.fetch_timeout.total_seconds()
            )
            entries = _parse_feed(feed_xml)
        except (ElementTree.ParseError, URLError, OSError, UnicodeError) as exc:
            return AdapterPollResult(
                errors=[AdapterItemError(error=str(exc), url=self.feed_url)],
                next_marker=last_seen_marker,
            )

        items: list[ContentItem] = []
        newest_marker = last_seen_marker
        for entry in sorted(entries, key=lambda item: item.marker):
            if not is_marker_newer(entry.marker, last_seen_marker):
                continue
            items.append(
                build_content_item(
                    content=entry.content,
                    source="rss",
                    timestamp=entry.timestamp,
                    config=self.ingestion_config,
                    url=entry.url,
                    linked_urls=entry.linked_urls,
                    title=entry.title,
                    author=entry.author,
                )
            )
            if is_marker_newer(entry.marker, newest_marker):
                newest_marker = entry.marker

        return AdapterPollResult(items=items, next_marker=newest_marker)


def rss_adapter_factory(
    config: AdapterConfig, ingestion_config: IngestionConfig
) -> RssAdapter:
    return RssAdapter(config, ingestion_config)


def _fetch_feed_xml(feed_url: str, timeout_seconds: float) -> str:
    request = Request(feed_url, headers={"User-Agent": "phosphene-source-ingestion/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
    return raw.decode(encoding, errors="replace")


def _parse_feed(feed_xml: str) -> list[_FeedEntry]:
    root = ElementTree.fromstring(feed_xml)
    if _strip_namespace(root.tag) == "rss":
        channel = root.find("channel")
        return [_parse_rss_item(item) for item in (channel or root).findall("item")]
    if root.tag == f"{_ATOM_NS}feed" or _strip_namespace(root.tag) == "feed":
        return [_parse_atom_entry(entry) for entry in _findall(root, "entry")]
    return []


def _parse_rss_item(item: ElementTree.Element) -> _FeedEntry:
    title = _child_text(item, "title")
    url = _child_text(item, "link")
    author = _child_text(item, "author") or _child_text(item, f"{_DC_NS}creator")
    timestamp = _parse_datetime(
        _child_text(item, "pubDate") or _child_text(item, f"{_DC_NS}date")
    )
    content_html = (
        _child_text(item, f"{_CONTENT_NS}encoded")
        or _child_text(item, "description")
        or title
        or ""
    )
    body = html_to_text(content_html)
    marker = _entry_marker(
        timestamp,
        _child_text(item, "guid") or url or title or body.text,
    )
    return _FeedEntry(
        marker=marker,
        timestamp=timestamp,
        content=body.text or title or "",
        url=url,
        title=title,
        author=author,
        linked_urls=body.linked_urls,
    )


def _parse_atom_entry(entry: ElementTree.Element) -> _FeedEntry:
    title = _child_text(entry, "title")
    url = _atom_link(entry)
    author = _child_text(entry, "author/name")
    timestamp = _parse_datetime(_child_text(entry, "published") or _child_text(entry, "updated"))
    content_html = _child_text(entry, "content") or _child_text(entry, "summary") or title or ""
    body = html_to_text(content_html)
    marker = _entry_marker(timestamp, _child_text(entry, "id") or url or title or body.text)
    return _FeedEntry(
        marker=marker,
        timestamp=timestamp,
        content=body.text or title or "",
        url=url,
        title=title,
        author=author,
        linked_urls=body.linked_urls,
    )


def _findall(element: ElementTree.Element, path: str) -> list[ElementTree.Element]:
    matches = element.findall(path)
    if matches:
        return matches
    return element.findall(f"{_ATOM_NS}{path}")


def _child_text(element: ElementTree.Element, path: str) -> str | None:
    child = element.find(path)
    if child is None and not path.startswith("{"):
        child = element.find(f"{_ATOM_NS}{path}")
    if child is None and "/" in path and not path.startswith("{"):
        child = _find_child_path(element, path)
    if child is None:
        return None
    text = "".join(child.itertext()).strip()
    return text or None


def _find_child_path(element: ElementTree.Element, path: str) -> ElementTree.Element | None:
    current = element
    for part in path.split("/"):
        child = current.find(part)
        if child is None:
            child = current.find(f"{_ATOM_NS}{part}")
        if child is None:
            return None
        current = child
    return current


def _atom_link(entry: ElementTree.Element) -> str | None:
    links = _findall(entry, "link")
    for link in links:
        href = link.attrib.get("href")
        rel = link.attrib.get("rel", "alternate")
        if href and rel == "alternate":
            return href
    return links[0].attrib.get("href") if links else None


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, timezone.utc)
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _entry_marker(timestamp: datetime, stable_id: str | None) -> str:
    return f"{timestamp.isoformat()} {stable_id or ''}"


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
