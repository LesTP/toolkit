"""Local corpus source adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape as html_unescape
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from toolkit.source_ingestion.adapters import (
    AdapterItemError,
    AdapterPollResult,
    LastSeenMarker,
)
from toolkit.source_ingestion.normalization import (
    build_content_item,
    fetch_url_text,
    html_to_text,
    is_marker_newer,
)
from toolkit.source_ingestion.types import AdapterConfig, ContentItem, IngestionConfig

_MARKDOWN_SUFFIXES = {".md", ".markdown"}
_HTML_SUFFIXES = {".html", ".htm"}
_JSON_SUFFIXES = {".json", ".js"}
_TEXT_SUFFIXES = {".txt", ".text"}
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_HTML_META_RE = re.compile(
    r"<meta\s+[^>]*(?:name|property)=[\"'](?:date|article:published_time|pubdate)[\"'][^>]*>",
    re.IGNORECASE,
)
_HTML_CONTENT_RE = re.compile(r"content=[\"']([^\"']+)[\"']", re.IGNORECASE)
_HTML_TIME_RE = re.compile(
    r"<time\s+[^>]*datetime=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE
)
_LJSM_DATE_RE = re.compile(
    r"(\d{4})</a>-<a[^>]*>(\d{2})</a>-<a[^>]*>(\d{2})</a>\s+(\d{2}:\d{2}:\d{2})"
)
_LJSM_COMMENTS_RE = re.compile(
    r"<div\s+id=[\"']Comments[\"'].*", re.DOTALL | re.IGNORECASE
)
_LJSM_CONTENT_RE = re.compile(
    r"<div\s+style=[\"']margin-left:\s*30px[\"']>(.*?)(?:</div>\s*<br|</div>\s*$)",
    re.DOTALL,
)
_LJSM_COMMENT_RE = re.compile(
    r"<table\s+id=[\"']ljcmt(\d+)[\"'][^>]*>.*?</table>",
    re.DOTALL,
)
_LJSM_COMMENT_USER_RE = re.compile(
    r"lj:user=[\"']([^\"']+)[\"']",
)
_LJSM_COMMENT_PARENT_RE = re.compile(
    r'<a\s+href=["\'][^"\']*thread=(\d+)[^"\']*["\'][^>]*>Parent</a>',
    re.IGNORECASE,
)


@dataclass
class _CorpusDocument:
    path: Path
    timestamp: datetime
    title: str | None
    author: str | None
    parts: list[str]
    linked_urls: list[str]


class CorpusTextAdapter:
    """Import plain text corpus files from a local path."""

    def __init__(self, config: AdapterConfig, ingestion_config: IngestionConfig) -> None:
        self.config = config
        self.ingestion_config = ingestion_config
        self.archive_path = Path(str(config.params["archive_path"]))

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        return _poll_local_corpus(
            archive_path=self.archive_path,
            source="corpus_text",
            allowed_suffixes=_TEXT_SUFFIXES,
            parse_document=_parse_text_document,
            last_seen_marker=last_seen_marker,
            ingestion_config=self.ingestion_config,
        )


class CorpusBlogAdapter:
    """Import markdown or HTML blog archives from a local path."""

    def __init__(self, config: AdapterConfig, ingestion_config: IngestionConfig) -> None:
        self.config = config
        self.ingestion_config = ingestion_config
        self.archive_path = Path(str(config.params["archive_path"]))
        self.file_format = str(config.params["format"])

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        if self.file_format == "markdown":
            allowed_suffixes = _MARKDOWN_SUFFIXES
            parser = _parse_markdown_document
        else:
            allowed_suffixes = _HTML_SUFFIXES
            parser = _parse_html_document

        return _poll_local_corpus(
            archive_path=self.archive_path,
            source="corpus_blog",
            allowed_suffixes=allowed_suffixes,
            parse_document=parser,
            last_seen_marker=last_seen_marker,
            ingestion_config=self.ingestion_config,
        )


class CorpusLiveJournalAdapter:
    """Import LiveJournal-style HTML exports from a local path.

    Supports two formats via ``config.params["format"]``:

    * ``"html"`` (default) — generic LJ HTML exports with ``<time>`` or
      ``<meta>`` date tags.
    * ``"ljsm"`` — ljsm (LiveJournal Suck Machine) backups.  Extracts
      dates from the linked ``YYYY-MM-DD HH:MM:SS`` pattern in the page
      body and strips the comments section.
    """

    def __init__(self, config: AdapterConfig, ingestion_config: IngestionConfig) -> None:
        self.config = config
        self.ingestion_config = ingestion_config
        self.archive_path = Path(str(config.params["archive_path"]))
        fmt = config.params.get("format", "html")
        self._parser = _parse_ljsm_html_document if fmt == "ljsm" else _parse_html_document

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        return _poll_local_corpus(
            archive_path=self.archive_path,
            source="corpus_livejournal",
            allowed_suffixes=_HTML_SUFFIXES,
            parse_document=self._parser,
            last_seen_marker=last_seen_marker,
            ingestion_config=self.ingestion_config,
        )


class CorpusTwitterAdapter:
    """Import Twitter/X JSON archive exports from a local path."""

    def __init__(self, config: AdapterConfig, ingestion_config: IngestionConfig) -> None:
        self.config = config
        self.ingestion_config = ingestion_config
        self.archive_path = Path(str(config.params["archive_path"]))

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        try:
            paths = _iter_archive_files(self.archive_path, _JSON_SUFFIXES)
        except OSError as exc:
            return AdapterPollResult(
                errors=[AdapterItemError(error=str(exc), url=str(self.archive_path))],
                next_marker=last_seen_marker,
            )

        items: list[ContentItem] = []
        errors: list[AdapterItemError] = []
        newest_marker = last_seen_marker

        for path in paths:
            try:
                tweets = _load_twitter_tweets(path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                errors.append(AdapterItemError(error=str(exc), url=str(path)))
                continue

            for index, tweet in enumerate(tweets):
                timestamp = _twitter_timestamp(tweet) or _file_timestamp(path)
                marker = _document_marker(path, timestamp, index)
                if not is_marker_newer(marker, last_seen_marker):
                    continue

                item, item_errors = _twitter_item(
                    tweet=tweet,
                    path=path,
                    timestamp=timestamp,
                    ingestion_config=self.ingestion_config,
                )
                items.append(item)
                errors.extend(item_errors)
                if is_marker_newer(marker, newest_marker):
                    newest_marker = marker

        return AdapterPollResult(items=items, errors=errors, next_marker=newest_marker)


class CorpusFacebookAdapter:
    """Import Facebook HTML data export.

    Parses the ``your_posts__check_ins__photos_and_videos`` HTML file
    exported by Facebook's "Download Your Information" tool.

    Config params:
        archive_path: Path to the HTML file (or directory containing them).
    """

    def __init__(self, config: AdapterConfig, ingestion_config: IngestionConfig) -> None:
        self.config = config
        self.ingestion_config = ingestion_config
        self.archive_path = Path(str(config.params["archive_path"]))

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        try:
            if self.archive_path.is_file():
                paths = [self.archive_path]
            elif self.archive_path.is_dir():
                paths = sorted(self.archive_path.glob("*.html"))
            else:
                raise FileNotFoundError(f"not found: {self.archive_path}")
        except OSError as exc:
            return AdapterPollResult(
                errors=[AdapterItemError(error=str(exc), url=str(self.archive_path))],
                next_marker=last_seen_marker,
            )

        items: list[ContentItem] = []
        errors: list[AdapterItemError] = []
        newest_marker = last_seen_marker

        for path in paths:
            try:
                new_items = _parse_facebook_html(path, last_seen_marker, self.ingestion_config)
                items.extend(new_items)
            except (OSError, UnicodeError) as exc:
                errors.append(AdapterItemError(error=str(exc), url=str(path)))

        for item in items:
            marker = f"{item.timestamp.timestamp():020.6f}:{item.url or ''}:000000"
            if is_marker_newer(marker, newest_marker):
                newest_marker = marker

        return AdapterPollResult(items=items, errors=errors, next_marker=newest_marker)


def corpus_facebook_adapter_factory(
    config: AdapterConfig, ingestion_config: IngestionConfig
) -> CorpusFacebookAdapter:
    return CorpusFacebookAdapter(config, ingestion_config)


class CorpusConversationsAdapter:
    """Import conversation history exports from local JSON or text files."""

    def __init__(self, config: AdapterConfig, ingestion_config: IngestionConfig) -> None:
        self.config = config
        self.ingestion_config = ingestion_config
        self.archive_path = Path(str(config.params["archive_path"]))
        self.file_format = str(config.params["format"])

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        if self.file_format == "json":
            return _poll_json_conversations(
                archive_path=self.archive_path,
                last_seen_marker=last_seen_marker,
                ingestion_config=self.ingestion_config,
            )

        return _poll_local_corpus(
            archive_path=self.archive_path,
            source="corpus_conversations",
            allowed_suffixes=_TEXT_SUFFIXES,
            parse_document=_parse_text_conversation_document,
            last_seen_marker=last_seen_marker,
            ingestion_config=self.ingestion_config,
        )


def corpus_text_adapter_factory(
    config: AdapterConfig, ingestion_config: IngestionConfig
) -> CorpusTextAdapter:
    return CorpusTextAdapter(config, ingestion_config)


def corpus_blog_adapter_factory(
    config: AdapterConfig, ingestion_config: IngestionConfig
) -> CorpusBlogAdapter:
    return CorpusBlogAdapter(config, ingestion_config)


def corpus_livejournal_adapter_factory(
    config: AdapterConfig, ingestion_config: IngestionConfig
) -> CorpusLiveJournalAdapter:
    return CorpusLiveJournalAdapter(config, ingestion_config)


class CorpusBlogspotAdapter:
    """Import Blogger/Blogspot Atom XML exports.

    Parses the Atom feed, extracts posts and (optionally) the journal
    owner's comment replies with parent context.  Other people's comments
    are skipped.

    Config params:
        archive_path: Path to the .atom file (or directory containing .atom files).
        author_name: Name to match for identifying the journal owner's comments
                     (default: inferred from the first POST entry's author).
    """

    def __init__(self, config: AdapterConfig, ingestion_config: IngestionConfig) -> None:
        self.config = config
        self.ingestion_config = ingestion_config
        self.archive_path = Path(str(config.params["archive_path"]))
        self._author_name: str | None = config.params.get("author_name")

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        try:
            if self.archive_path.is_file():
                paths = [self.archive_path]
            elif self.archive_path.is_dir():
                paths = sorted(self.archive_path.glob("*.atom"))
            else:
                raise FileNotFoundError(f"not found: {self.archive_path}")
        except OSError as exc:
            return AdapterPollResult(
                errors=[AdapterItemError(error=str(exc), url=str(self.archive_path))],
                next_marker=last_seen_marker,
            )

        items: list[ContentItem] = []
        errors: list[AdapterItemError] = []
        newest_marker = last_seen_marker

        for path in paths:
            try:
                new_items = _parse_blogspot_atom(
                    path, self._author_name, last_seen_marker, self.ingestion_config
                )
                items.extend(new_items)
            except (OSError, UnicodeError, ET.ParseError) as exc:
                errors.append(AdapterItemError(error=str(exc), url=str(path)))
                continue

        # Compute newest marker from items
        for item in items:
            marker = f"{item.timestamp.timestamp():020.6f}:{item.url or ''}:000000"
            if is_marker_newer(marker, newest_marker):
                newest_marker = marker

        return AdapterPollResult(items=items, errors=errors, next_marker=newest_marker)


def corpus_blogspot_adapter_factory(
    config: AdapterConfig, ingestion_config: IngestionConfig
) -> CorpusBlogspotAdapter:
    return CorpusBlogspotAdapter(config, ingestion_config)


def corpus_twitter_adapter_factory(
    config: AdapterConfig, ingestion_config: IngestionConfig
) -> CorpusTwitterAdapter:
    return CorpusTwitterAdapter(config, ingestion_config)


def corpus_conversations_adapter_factory(
    config: AdapterConfig, ingestion_config: IngestionConfig
) -> CorpusConversationsAdapter:
    return CorpusConversationsAdapter(config, ingestion_config)


def _poll_local_corpus(
    *,
    archive_path: Path,
    source: str,
    allowed_suffixes: set[str],
    parse_document: Callable[[Path], _CorpusDocument],
    last_seen_marker: LastSeenMarker,
    ingestion_config: IngestionConfig,
) -> AdapterPollResult:
    try:
        paths = _iter_archive_files(archive_path, allowed_suffixes)
    except OSError as exc:
        return AdapterPollResult(
            errors=[AdapterItemError(error=str(exc), url=str(archive_path))],
            next_marker=last_seen_marker,
        )

    items: list[ContentItem] = []
    errors: list[AdapterItemError] = []
    newest_marker = last_seen_marker

    for path in paths:
        try:
            document = parse_document(path)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(AdapterItemError(error=str(exc), url=str(path)))
            continue

        for index, part in enumerate(document.parts):
            marker = _document_marker(document.path, document.timestamp, index)
            if not is_marker_newer(marker, last_seen_marker):
                continue
            items.append(
                build_content_item(
                    content=part,
                    source=source,
                    timestamp=document.timestamp,
                    config=ingestion_config,
                    url=str(document.path),
                    linked_urls=document.linked_urls,
                    title=document.title,
                    author=document.author,
                )
            )
            if is_marker_newer(marker, newest_marker):
                newest_marker = marker

    return AdapterPollResult(items=items, errors=errors, next_marker=newest_marker)


def _iter_archive_files(archive_path: Path, allowed_suffixes: set[str]) -> list[Path]:
    if not archive_path.exists():
        raise FileNotFoundError(f"archive path not found: {archive_path}")
    if archive_path.is_file():
        return [archive_path] if archive_path.suffix.lower() in allowed_suffixes else []
    if not archive_path.is_dir():
        raise OSError(f"archive path is not a file or directory: {archive_path}")
    return sorted(
        path
        for path in archive_path.rglob("*")
        if path.is_file()
        and not any(part.startswith(".") for part in path.parts)
        and path.suffix.lower() in allowed_suffixes
    )


def _parse_text_document(path: Path) -> _CorpusDocument:
    content = path.read_text(encoding="utf-8")
    return _CorpusDocument(
        path=path,
        timestamp=_file_timestamp(path),
        title=path.stem,
        author=None,
        parts=_split_text_parts(content),
        linked_urls=[],
    )


def _parse_markdown_document(path: Path) -> _CorpusDocument:
    content = path.read_text(encoding="utf-8")
    metadata, body = _split_frontmatter(content)
    title = metadata.get("title") or _first_markdown_heading(body) or path.stem
    timestamp = _parse_datetime(metadata.get("date")) or _file_timestamp(path)
    author = metadata.get("author")
    body = _HEADING_RE.sub("", body).strip() if metadata.get("title") else body
    return _CorpusDocument(
        path=path,
        timestamp=timestamp,
        title=title,
        author=author,
        parts=_split_text_parts(_strip_markdown_markup(body)),
        linked_urls=[],
    )


def _parse_html_document(path: Path) -> _CorpusDocument:
    content = path.read_text(encoding="utf-8")
    extracted = html_to_text(content)
    timestamp = _html_datetime(content) or _file_timestamp(path)
    return _CorpusDocument(
        path=path,
        timestamp=timestamp,
        title=extracted.title or path.stem,
        author=None,
        parts=_split_text_parts(extracted.text),
        linked_urls=extracted.linked_urls or [],
    )


def _extract_ljsm_comment_replies(
    html: str, journal_user: str = "lestp",
) -> list[str]:
    """Extract the journal owner's comment replies with parent context.

    Returns a list of text parts, each formatted as:
        [context: username] parent comment text
        [reply] your reply text
    """
    # Parse all comments into a dict: comment_id -> (user, body_html)
    comments: dict[str, tuple[str, str]] = {}
    for match in _LJSM_COMMENT_RE.finditer(html):
        cmt_id = match.group(1)
        cmt_html = match.group(0)
        user_match = _LJSM_COMMENT_USER_RE.search(cmt_html)
        if not user_match:
            continue
        user = user_match.group(1)
        # Extract comment body: second <td> in the table (after the header row)
        body_match = re.search(
            r"</tr>\s*<tr[^>]*>\s*<td>(.*?)</td>\s*</tr>",
            cmt_html,
            re.DOTALL,
        )
        if not body_match:
            continue
        comments[cmt_id] = (user, body_match.group(1))

    # Find parent relationships
    parent_map: dict[str, str] = {}
    for match in _LJSM_COMMENT_RE.finditer(html):
        cmt_id = match.group(1)
        parent_match = _LJSM_COMMENT_PARENT_RE.search(match.group(0))
        if parent_match:
            parent_map[cmt_id] = parent_match.group(1)

    # Build reply parts: only for journal_user's comments that have a parent
    parts: list[str] = []
    for cmt_id, (user, body_html) in comments.items():
        if user != journal_user:
            continue
        parent_id = parent_map.get(cmt_id)
        if not parent_id or parent_id not in comments:
            continue

        parent_user, parent_body_html = comments[parent_id]
        if parent_user == journal_user:
            continue  # skip self-replies (threading artifacts)

        parent_text = html_to_text(parent_body_html).text.strip()
        reply_text = html_to_text(body_html).text.strip()

        # Strip LJ navigation cruft from comment text
        parent_text = re.sub(
            r"\s*\(\s*(?:Reply to this|Thread|Parent)\s*\)\s*", "", parent_text
        ).strip()
        reply_text = re.sub(
            r"\s*\(\s*(?:Reply to this|Thread|Parent)\s*\)\s*", "", reply_text
        ).strip()

        if not reply_text:
            continue

        if parent_text:
            part = f"[context: {parent_user}] {parent_text}\n\n[reply] {reply_text}"
        else:
            part = reply_text
        parts.append(part)

    return parts


def _parse_ljsm_html_document(path: Path) -> _CorpusDocument:
    """Parse ljsm (LiveJournal Suck Machine) HTML exports.

    Strips the comments section and extracts only the post body from
    the ``margin-left: 30px`` content div.  Falls back to full-page
    extraction if the content div is not found.
    """
    content = path.read_text(encoding="utf-8")
    timestamp = _html_datetime(content) or _file_timestamp(path)

    # Try to extract just the post body from the content div
    body_match = _LJSM_CONTENT_RE.search(content)
    if body_match:
        body_html = body_match.group(1)
        # Strip metadata table (Current mood, Current music, Entry tags)
        body_html = re.sub(
            r"<table\b[^>]*>.*?</table>", "", body_html, count=1, flags=re.DOTALL
        )
    else:
        # Fall back: strip comments section if present, use full page
        body_html = _LJSM_COMMENTS_RE.sub("", content)

    extracted = html_to_text(body_html)
    # Title from <title> of the full page (not the stripped body)
    full_extracted = html_to_text(content)
    title = full_extracted.title or path.stem
    # Strip "username: " prefix from ljsm titles
    if title and ": " in title:
        title = title.split(": ", 1)[1]

    return _CorpusDocument(
        path=path,
        timestamp=timestamp,
        title=title,
        author=None,
        parts=_split_text_parts(extracted.text) + _extract_ljsm_comment_replies(content),
        linked_urls=extracted.linked_urls or [],
    )


def _parse_text_conversation_document(path: Path) -> _CorpusDocument:
    content = path.read_text(encoding="utf-8")
    return _CorpusDocument(
        path=path,
        timestamp=_file_timestamp(path),
        title=path.stem,
        author=None,
        parts=_split_text_parts(content),
        linked_urls=[],
    )


def _poll_json_conversations(
    *,
    archive_path: Path,
    last_seen_marker: LastSeenMarker,
    ingestion_config: IngestionConfig,
) -> AdapterPollResult:
    try:
        paths = _iter_archive_files(archive_path, {".json"})
    except OSError as exc:
        return AdapterPollResult(
            errors=[AdapterItemError(error=str(exc), url=str(archive_path))],
            next_marker=last_seen_marker,
        )

    items: list[ContentItem] = []
    errors: list[AdapterItemError] = []
    newest_marker = last_seen_marker

    for path in paths:
        try:
            conversations = _load_conversations(path)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(AdapterItemError(error=str(exc), url=str(path)))
            continue

        for index, message in enumerate(_iter_conversation_messages(conversations)):
            timestamp = message["timestamp"] or _file_timestamp(path)
            marker = _document_marker(path, timestamp, index)
            if not is_marker_newer(marker, last_seen_marker):
                continue
            items.append(
                build_content_item(
                    content=message["content"],
                    source="corpus_conversations",
                    timestamp=timestamp,
                    config=ingestion_config,
                    url=str(path),
                    title=message["title"],
                    author=message["author"],
                )
            )
            if is_marker_newer(marker, newest_marker):
                newest_marker = marker

    return AdapterPollResult(items=items, errors=errors, next_marker=newest_marker)


def _load_json_or_js(path: Path) -> object:
    content = path.read_text(encoding="utf-8")
    stripped = content.strip()
    if not stripped:
        raise ValueError("archive file is empty")
    if stripped[0] not in "[{":
        starts = [index for index in (stripped.find("["), stripped.find("{")) if index >= 0]
        if not starts:
            raise ValueError("archive file does not contain JSON")
        stripped = stripped[min(starts) :]
    decoder = json.JSONDecoder()
    value, _ = decoder.raw_decode(stripped)
    return value


def _load_twitter_tweets(path: Path) -> list[dict]:
    data = _load_json_or_js(path)
    tweets: list[dict] = []
    seen: set[str] = set()
    for value in _walk_json(data):
        if isinstance(value, dict) and "tweet" in value and isinstance(value["tweet"], dict):
            tweet = value["tweet"]
        elif isinstance(value, dict) and (
            "full_text" in value or "created_at" in value or "entities" in value
        ):
            tweet = value
        else:
            continue

        identity = str(tweet.get("id_str") or tweet.get("id") or id(tweet))
        if identity in seen:
            continue
        seen.add(identity)
        tweets.append(tweet)
    if not tweets:
        raise ValueError("no tweets found in archive")
    return tweets


def _load_conversations(path: Path) -> object:
    data = _load_json_or_js(path)
    if not isinstance(data, dict | list):
        raise ValueError("conversation archive must be an object or list")
    return data


def _iter_conversation_messages(data: object) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []

    def visit(value: object, title: str | None = None) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item, title)
            return
        if not isinstance(value, dict):
            return

        next_title = _string_value(value, "title", "name", "conversation_title") or title
        nested = value.get("messages") or value.get("chat_messages") or value.get("mapping")
        if nested is not None:
            visit(nested, next_title)

        content = _message_content(value)
        if not content:
            return
        messages.append(
            {
                "content": content,
                "title": next_title,
                "author": _message_author(value),
                "timestamp": _message_timestamp(value),
            }
        )

    visit(data)
    return messages


def _walk_json(value: object) -> list[object]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(_walk_json(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk_json(child))
    return values


def _twitter_item(
    *,
    tweet: dict,
    path: Path,
    timestamp: datetime,
    ingestion_config: IngestionConfig,
) -> tuple[ContentItem, list[AdapterItemError]]:
    text = _tweet_text(tweet)
    links = _tweet_urls(tweet)
    author = _tweet_author(tweet)
    annotation = _strip_urls(text).strip() or None
    title = f"Tweet {tweet.get('id_str') or tweet.get('id') or path.stem}"
    errors: list[AdapterItemError] = []

    if links:
        url = links[0]
        try:
            fetched = fetch_url_text(
                url, ingestion_config.fetch_timeout.total_seconds()
            )
        except Exception as exc:  # noqa: BLE001 - archive link failures are per-item.
            content = annotation or text or url
            title = title if annotation else f"Linked tweet {url}"
            errors.append(AdapterItemError(error=str(exc), url=url))
            linked_urls = links
        else:
            content = fetched.text or annotation or text or url
            title = fetched.title or title
            linked_urls = [*links, *(fetched.linked_urls or [])]

        return (
            build_content_item(
                content=content,
                source="corpus_twitter",
                timestamp=timestamp,
                config=ingestion_config,
                url=url,
                linked_urls=linked_urls,
                title=title,
                author=author,
                human_annotation=annotation,
            ),
            errors,
        )

    content = annotation or text
    if _is_uncommented_retweet(tweet, text):
        title = f"Retweet {tweet.get('id_str') or tweet.get('id') or path.stem}"
    return (
        build_content_item(
            content=content,
            source="corpus_twitter",
            timestamp=timestamp,
            config=ingestion_config,
            url=None,
            linked_urls=[],
            title=title,
            author=author,
            human_annotation=None if _is_uncommented_retweet(tweet, text) else annotation,
        ),
        errors,
    )


def _tweet_text(tweet: dict) -> str:
    value = tweet.get("full_text") or tweet.get("text") or tweet.get("tweet_text") or ""
    return str(value).strip()


def _tweet_urls(tweet: dict) -> list[str]:
    urls: list[str] = []
    entity_short_urls: set[str] = set()
    entities = tweet.get("entities")
    if isinstance(entities, dict):
        for entry in entities.get("urls") or []:
            if not isinstance(entry, dict):
                continue
            short_url = entry.get("url")
            if short_url:
                entity_short_urls.add(str(short_url))
            url = entry.get("expanded_url") or short_url
            if url:
                urls.append(str(url))
    urls.extend(
        url
        for url in re.findall(r"https?://\S+", _tweet_text(tweet))
        if url.rstrip(".,;:!?)]}") not in entity_short_urls
    )

    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        normalized = url.rstrip(".,;:!?)]}")
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _tweet_author(tweet: dict) -> str | None:
    user = tweet.get("user") or tweet.get("account")
    if isinstance(user, dict):
        return _string_value(user, "screen_name", "name", "username")
    return _string_value(tweet, "screen_name", "username", "author")


def _twitter_timestamp(tweet: dict) -> datetime | None:
    created_at = _string_value(tweet, "created_at", "createdAt", "timestamp")
    parsed = _parse_datetime(created_at)
    if parsed is not None:
        return parsed
    if created_at:
        try:
            return datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y").astimezone(
                timezone.utc
            )
        except ValueError:
            return None
    return None


def _is_uncommented_retweet(tweet: dict, text: str) -> bool:
    return bool(tweet.get("retweeted_status")) or text.startswith("RT @")


def _strip_urls(text: str) -> str:
    return re.sub(r"https?://\S+", "", text).strip()


def _message_content(message: dict) -> str | None:
    value = message.get("content") or message.get("text") or message.get("message")
    if isinstance(value, list):
        parts: list[str] = []
        for part in value:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if text:
                    parts.append(str(text))
        value = " ".join(parts)
    if isinstance(value, dict):
        value = value.get("text") or value.get("content")
    if not value:
        return None
    return str(value).strip() or None


def _message_author(message: dict) -> str | None:
    author = message.get("author") or message.get("role") or message.get("sender")
    if isinstance(author, dict):
        return _string_value(author, "name", "role", "username")
    return str(author) if author else None


def _message_timestamp(message: dict) -> datetime | None:
    value = _string_value(
        message, "timestamp", "created_at", "createdAt", "date", "datetime"
    )
    parsed = _parse_datetime(value)
    if parsed is not None:
        return parsed
    numeric = message.get("create_time") or message.get("created")
    if isinstance(numeric, int | float):
        return datetime.fromtimestamp(float(numeric), timezone.utc)
    return None


def _string_value(value: dict, *keys: str) -> str | None:
    for key in keys:
        item = value.get(key)
        if item is not None and item != "":
            return str(item)
    return None


def _split_frontmatter(content: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip().lower()] = value.strip().strip("\"'")
    return metadata, content[match.end() :]


def _first_markdown_heading(content: str) -> str | None:
    match = _HEADING_RE.search(content)
    return match.group(1).strip() if match else None


def _strip_markdown_markup(content: str) -> str:
    content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    content = re.sub(r"`([^`]+)`", r"\1", content)
    content = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", content)
    content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 \2", content)
    content = re.sub(r"^\s{0,3}#{1,6}\s+", "", content, flags=re.MULTILINE)
    content = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", content)
    return content.strip()


def _split_text_parts(content: str) -> list[str]:
    paragraphs = [
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n+", content)
    ]
    return [paragraph for paragraph in paragraphs if paragraph]


def _file_timestamp(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _html_datetime(content: str) -> datetime | None:
    time_match = _HTML_TIME_RE.search(content)
    if time_match:
        parsed = _parse_datetime(time_match.group(1))
        if parsed is not None:
            return parsed

    meta_match = _HTML_META_RE.search(content)
    if meta_match:
        content_match = _HTML_CONTENT_RE.search(meta_match.group(0))
        if content_match:
            parsed = _parse_datetime(content_match.group(1))
            if parsed is not None:
                return parsed

    ljsm_match = _LJSM_DATE_RE.search(content)
    if ljsm_match:
        date_str = f"{ljsm_match.group(1)}-{ljsm_match.group(2)}-{ljsm_match.group(3)} {ljsm_match.group(4)}"
        return _parse_datetime(date_str)

    return None


_ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "blogger": "http://schemas.google.com/blogger/2018",
}

_FB_POST_RE = re.compile(r'<div class="_2pin">')
_FB_TIMESTAMP_RE = re.compile(
    r"(?:Updated|Created)\s+(\w+ \d+,\s*\d{4}\s+\d+:\d+:\d+)\s*(?:AM|PM|am|pm)?"
)
_FB_TAG_RE = re.compile(r"@\[\d+:\d+:([^\]]+)\]")
_FB_BOILERPLATE_RE = re.compile(
    r"\s*(?:Mike Yeluashvili|Michael Yeluashvili)\s+(?:shared a link|shared a post|shared a photo|added a new photo|posted|updated|wrote on)[^.]*\.?",
    re.IGNORECASE,
)


def _parse_fb_timestamp(raw: str) -> datetime | None:
    """Parse Facebook export timestamp like 'Aug 12, 2009 3:54:40'."""
    raw = raw.strip()
    for fmt in ("%b %d, %Y %H:%M:%S", "%b %d,%Y %H:%M:%S", "%B %d, %Y %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _parse_facebook_html(
    path: Path,
    last_seen_marker: LastSeenMarker,
    ingestion_config: IngestionConfig,
) -> list[ContentItem]:
    """Parse Facebook HTML data export into ContentItems."""
    content = path.read_text(encoding="utf-8")
    blocks = _FB_POST_RE.split(content)[1:]  # skip header

    items: list[ContentItem] = []

    for block in blocks:
        # Extract timestamp
        ts_match = _FB_TIMESTAMP_RE.search(block)
        if not ts_match:
            continue  # skip blocks without timestamps (media-only halves)

        timestamp = _parse_fb_timestamp(ts_match.group(1))
        if timestamp is None:
            continue

        # Extract text: strip HTML, decode entities
        text = re.sub(r"<[^>]+>", " ", block)
        text = html_unescape(text).strip()
        text = re.sub(r"\s+", " ", text)

        # Clean FB user tags: @[id:hash:Name] -> @Name
        text = _FB_TAG_RE.sub(r"@\1", text)

        # Remove the timestamp text and boilerplate from content
        text = _FB_TIMESTAMP_RE.sub("", text).strip()
        text = _FB_BOILERPLATE_RE.sub("", text).strip()

        if not text or len(text.split()) < 5:
            continue

        items.append(
            build_content_item(
                content=text,
                source="corpus_facebook",
                timestamp=timestamp,
                config=ingestion_config,
                url=str(path),
                title=None,
                author=None,
            )
        )

    return items


def _parse_blogspot_atom(
    path: Path,
    author_name: str | None,
    last_seen_marker: LastSeenMarker,
    ingestion_config: IngestionConfig,
) -> list[ContentItem]:
    """Parse a Blogger Atom XML export into ContentItems.

    Extracts POST entries as primary content and the journal owner's
    COMMENT replies with parent context.
    """
    tree = ET.parse(path)
    root = tree.getroot()

    # Index all entries by ID
    posts: dict[str, ET.Element] = {}
    comments: list[ET.Element] = []

    for entry in root.findall("atom:entry", _ATOM_NS):
        btype = entry.find("blogger:type", _ATOM_NS)
        if btype is None:
            continue
        entry_id = entry.findtext("atom:id", "", _ATOM_NS)
        if btype.text == "POST":
            posts[entry_id] = entry
        elif btype.text == "COMMENT":
            comments.append(entry)

    # Infer author name from first post if not provided
    if author_name is None:
        for entry in posts.values():
            name_el = entry.find("atom:author/atom:name", _ATOM_NS)
            if name_el is not None and name_el.text:
                author_name = name_el.text
                break

    items: list[ContentItem] = []

    # Process posts
    for entry_id, entry in posts.items():
        timestamp = _blogspot_timestamp(entry)
        if timestamp is None:
            continue

        content_el = entry.find("atom:content", _ATOM_NS)
        if content_el is None or not content_el.text:
            continue

        title_el = entry.find("atom:title", _ATOM_NS)
        title = title_el.text if title_el is not None and title_el.text else None

        # Content is HTML — extract text
        extracted = html_to_text(content_el.text)
        text = extracted.text.strip()
        if not text:
            continue

        # Categories as tags
        categories = [
            cat.get("term", "")
            for cat in entry.findall("atom:category", _ATOM_NS)
            if cat.get("term")
        ]

        for part in _split_text_parts(text):
            items.append(
                build_content_item(
                    content=part,
                    source="corpus_blogspot",
                    timestamp=timestamp,
                    config=ingestion_config,
                    url=str(path),
                    linked_urls=extracted.linked_urls or [],
                    title=title,
                    author=author_name,
                )
            )

    # Process author's comment replies with parent context
    if author_name:
        # Build a map of post ID -> post content for context
        post_content_by_id: dict[str, str] = {}
        for entry_id, entry in posts.items():
            content_el = entry.find("atom:content", _ATOM_NS)
            if content_el is not None and content_el.text:
                post_content_by_id[entry_id] = html_to_text(content_el.text).text.strip()

        # Build comment-by-ID map for comment-on-comment context
        comment_by_id: dict[str, ET.Element] = {}
        for cmt in comments:
            cmt_id = cmt.findtext("atom:id", "", _ATOM_NS)
            if cmt_id:
                comment_by_id[cmt_id] = cmt

        for cmt in comments:
            # Only the journal owner's comments
            cmt_author = cmt.find("atom:author/atom:name", _ATOM_NS)
            if cmt_author is None or cmt_author.text != author_name:
                continue

            content_el = cmt.find("atom:content", _ATOM_NS)
            if content_el is None or not content_el.text:
                continue

            reply_text = html_to_text(content_el.text).text.strip()
            if not reply_text:
                continue

            timestamp = _blogspot_timestamp(cmt)
            if timestamp is None:
                continue

            # Find parent — could be the post or another comment
            parent_el = cmt.find("blogger:parent", _ATOM_NS)
            parent_id = parent_el.text if parent_el is not None and parent_el.text else None

            context_text = ""
            context_user = ""
            if parent_id and parent_id in comment_by_id:
                # Parent is a comment
                parent_cmt = comment_by_id[parent_id]
                parent_author = parent_cmt.find("atom:author/atom:name", _ATOM_NS)
                context_user = (parent_author.text or "?") if parent_author is not None else "?"
                parent_content = parent_cmt.find("atom:content", _ATOM_NS)
                if parent_content is not None and parent_content.text:
                    context_text = html_to_text(parent_content.text).text.strip()
            if parent_id and parent_id in post_content_by_id:
                # Parent is the post — include as standalone follow-up comment
                items.append(
                    build_content_item(
                        content=reply_text,
                        source="corpus_blogspot",
                        timestamp=timestamp,
                        config=ingestion_config,
                        url=str(path),
                        title=None,
                        author=author_name,
                    )
                )
                continue

            if context_user == author_name:
                # Skip self-replies
                continue

            if context_text and context_user:
                part = f"[context: {context_user}] {context_text}\n\n[reply] {reply_text}"
            else:
                part = reply_text

            items.append(
                build_content_item(
                    content=part,
                    source="corpus_blogspot",
                    timestamp=timestamp,
                    config=ingestion_config,
                    url=str(path),
                    title=None,
                    author=author_name,
                )
            )

    return items


def _blogspot_timestamp(entry: ET.Element) -> datetime | None:
    """Extract timestamp from a Blogger Atom entry."""
    for tag in ("atom:published", "blogger:created"):
        el = entry.find(tag, _ATOM_NS)
        if el is not None and el.text:
            parsed = _parse_datetime(el.text)
            if parsed is not None:
                return parsed
    return None


def _document_marker(path: Path, timestamp: datetime, index: int) -> str:
    try:
        stable_path = str(path.resolve())
    except OSError:
        stable_path = str(path)
    return f"{timestamp.timestamp():020.6f}:{stable_path}:{index:06d}"
