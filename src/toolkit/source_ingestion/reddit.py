"""Reddit source adapter."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from urllib.parse import quote
from urllib.request import Request, urlopen

from toolkit.source_ingestion.adapters import (
    AdapterItemError,
    AdapterPollResult,
    LastSeenMarker,
)
from toolkit.source_ingestion.normalization import (
    build_content_item,
    is_marker_newer,
    marker_sort_key,
)
from toolkit.source_ingestion.types import AdapterConfig, ContentItem, IngestionConfig


@dataclass
class _RedditPost:
    marker: str
    timestamp: datetime
    content: str
    url: str | None = None
    title: str | None = None
    author: str | None = None


class RedditAdapter:
    """Poll subreddit listing posts through a small HTTP/API boundary."""

    def __init__(self, config: AdapterConfig, ingestion_config: IngestionConfig) -> None:
        self.config = config
        self.ingestion_config = ingestion_config
        credentials = config.credentials or {}
        self.subreddit = str(config.params["subreddit"])
        self.sort = str(config.params["sort"])
        self.client = _create_reddit_client(
            client_id=str(credentials["client_id"]),
            client_secret=str(credentials["client_secret"]),
            timeout_seconds=ingestion_config.fetch_timeout.total_seconds(),
        )

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        try:
            raw_posts = self.client.fetch_posts(self.subreddit, self.sort)
        except Exception as exc:  # noqa: BLE001 - API failures stay in result errors.
            return AdapterPollResult(
                errors=[AdapterItemError(error=str(exc), url=_listing_url(self.subreddit, self.sort))],
                next_marker=last_seen_marker,
            )

        posts = [
            post
            for raw_post in raw_posts
            if (post := _normalize_post(raw_post)) is not None
        ]

        items: list[ContentItem] = []
        newest_marker = last_seen_marker
        for post in sorted(posts, key=lambda item: marker_sort_key(item.marker)):
            if not is_marker_newer(post.marker, last_seen_marker):
                continue
            items.append(
                build_content_item(
                    content=post.content,
                    source="reddit",
                    timestamp=post.timestamp,
                    config=self.ingestion_config,
                    url=post.url,
                    linked_urls=[post.url] if post.url else None,
                    title=post.title,
                    author=post.author,
                )
            )
            if is_marker_newer(post.marker, newest_marker):
                newest_marker = post.marker

        return AdapterPollResult(items=items, next_marker=newest_marker)


def reddit_adapter_factory(
    config: AdapterConfig, ingestion_config: IngestionConfig
) -> RedditAdapter:
    return RedditAdapter(config, ingestion_config)


class _RedditApiClient:
    def __init__(
        self, *, client_id: str, client_secret: str, timeout_seconds: float
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout_seconds = timeout_seconds

    def fetch_posts(self, subreddit: str, sort: str) -> Iterable[object]:
        request = Request(
            _listing_url(subreddit, sort),
            headers={
                "Accept": "application/json",
                "User-Agent": f"phosphene-source-ingestion/0.1 ({self.client_id})",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _children_from_listing(payload)


def _create_reddit_client(
    *, client_id: str, client_secret: str, timeout_seconds: float
) -> _RedditApiClient:
    return _RedditApiClient(
        client_id=client_id,
        client_secret=client_secret,
        timeout_seconds=timeout_seconds,
    )


def _children_from_listing(payload: object) -> list[object]:
    data = _field(payload, "data")
    children = _field(data, "children")
    if not isinstance(children, list):
        return []
    return [_field(child, "data") or child for child in children]


def _normalize_post(raw_post: object) -> _RedditPost | None:
    post_id = _field_as_str(raw_post, "id")
    title = _field_as_str(raw_post, "title")
    selftext = _field_as_str(raw_post, "selftext")
    created = _field(raw_post, "created_utc") or _field(raw_post, "created")
    timestamp = _timestamp(created)
    marker = _post_marker(timestamp, post_id or title or "")
    content = "\n".join(part for part in (title, selftext) if part).strip()
    if not content:
        return None

    return _RedditPost(
        marker=marker,
        timestamp=timestamp,
        content=content,
        url=_post_url(raw_post),
        title=title,
        author=_field_as_str(raw_post, "author"),
    )


def _post_url(raw_post: object) -> str | None:
    is_self = bool(_field(raw_post, "is_self"))
    url = _field_as_str(raw_post, "url")
    if url and not is_self:
        return url
    permalink = _field_as_str(raw_post, "permalink")
    if permalink:
        return f"https://www.reddit.com{permalink}"
    return url


def _timestamp(value: object) -> datetime:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value), timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromtimestamp(float(value), timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, timezone.utc)


def _post_marker(timestamp: datetime, stable_id: str) -> str:
    return f"{timestamp.timestamp():020.6f} {stable_id}"


def _listing_url(subreddit: str, sort: str) -> str:
    return f"https://www.reddit.com/r/{quote(subreddit.strip('/'))}/{sort}.json?limit=25"


def _field(value: object, key: str) -> object | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _field_as_str(value: object, key: str) -> str | None:
    field_value = _field(value, key)
    if field_value is None:
        return None
    text = str(field_value).strip()
    return text or None
