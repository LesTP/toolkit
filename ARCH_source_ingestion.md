# ARCH: Source Ingestion

> **Provenance:** Extracted from Phosphene's `source_ingestion/` module on 2026-06-02. Public API and adapter set unchanged. Phosphene's `ARCH_source_ingestion.md` now redirects here. The module is downstream-agnostic — content is normalised into `ContentItem` objects that any consumer (Phosphene's Attention Filter, or other projects) can process.

## Purpose
Adapters that pull content from external sources and normalize it into `ContentItem` objects for downstream processing. Each adapter is independent (leaf) with no cross-dependencies. Adapters cover both autonomous sources (channels the system monitors on its own) and human-curated sources (content the human explicitly shares). The adapter interface is uniform — downstream consumers don't care where content came from, only the `source` field distinguishes origin.

## Public API

### Types

```python
@dataclass
class ContentItem:
    content: str                                    # extracted text content
    source: str                                     # adapter identifier (e.g., "telegram_channel", "rss", "human_share")
    timestamp: datetime                             # when the content was published or shared
    url: str | None = None                          # source URL (if applicable)
    linked_urls: list[str] = field(default_factory=list)  # URLs found in content (for Explorer)
    title: str | None = None                        # article/post title (if available)
    author: str | None = None                       # original author (if available)
    human_annotation: str | None = None             # human's comment when sharing (human_share adapter only)

@dataclass
class AdapterConfig:
    adapter_type: str                               # "telegram_channel", "rss", "reddit", "human_share",
                                                     # "corpus_livejournal", "corpus_twitter", "corpus_blog",
                                                     # "corpus_conversations", "corpus_text"
    source_label: str                               # human-readable name (e.g., "Philosophy channel", "My shares")
    poll_interval: timedelta = timedelta(hours=4)   # how often to check for new content
    enabled: bool = True
    credentials: dict | None = None                 # adapter-specific auth (API keys, bot tokens, etc.)
    params: dict = field(default_factory=dict)      # adapter-specific parameters (channel_id, feed_url, subreddit, etc.)

@dataclass
class IngestionConfig:
    adapters: list[AdapterConfig]
    fetch_timeout: timedelta = timedelta(seconds=30)    # per-URL fetch timeout
    max_content_length: int = 50_000                    # max chars per content item (truncate beyond)
    extract_links: bool = True                          # parse content for URLs

@dataclass
class IngestionResult:
    items: list[ContentItem]                        # normalized content items
    adapter_label: str                              # which adapter produced these
    errors: list[IngestionError]                    # items that failed to fetch or parse
    poll_timestamp: datetime                        # when this poll ran

@dataclass
class IngestionError:
    url: str | None
    error: str
    adapter_label: str
```

### SourceIngestion (manager)

- **Signature:** `SourceIngestion(config: IngestionConfig)`
- **Parameters:**
  - config: IngestionConfig — list of adapters with their configs
- **Errors:**
  - `AdapterConfigError` — unknown adapter_type, missing required credentials or params

### poll

- **Signature:** `poll(adapter_label: str | None = None) -> list[IngestionResult]`
- **Parameters:**
  - adapter_label: str | None — poll a specific adapter. None = poll all enabled adapters.
- **Returns:** list[IngestionResult] — one per adapter polled. Each contains the new `ContentItem` objects since the last poll.
- **Errors:**
  - `AdapterNotFoundError` — adapter_label not recognized
  - Network/API errors are caught per-item and reported in `IngestionResult.errors`, not raised

### poll_once

- **Signature:** `poll_once(adapter_label: str) -> IngestionResult`
- **Parameters:**
  - adapter_label: str — single adapter to poll
- **Returns:** IngestionResult
- **Errors:**
  - `AdapterNotFoundError` — adapter_label not recognized

## Adapters

Each adapter implements a common internal interface: given its config and a "last seen" marker, fetch new content and return normalized `ContentItem` objects. Adding a new adapter is additive — implement the interface, register the adapter_type.

### telegram_channel

Monitors a public or joined Telegram channel for new posts. Uses toolkit/telegram_client for polling.

- **params:** `{"channel_id": str}` or `{"channel_username": str}`
- **credentials:** `{"bot_token": str}`
- **source field:** `"telegram_channel"`
- **Behavior:** Long-polls for new messages since last check. Extracts text, media captions, and forwarded content. Links in message text are extracted into `linked_urls`.

### rss

Fetches RSS/Atom feeds.

- **params:** `{"feed_url": str}`
- **credentials:** none
- **source field:** `"rss"`
- **Behavior:** Parses feed, returns entries newer than last poll. Content is the entry body (HTML stripped to text). `url` is the entry link. `title` and `author` populated from feed metadata.

### reddit

Fetches posts from a subreddit.

- **params:** `{"subreddit": str, "sort": str}` — sort is "new", "hot", or "top"
- **credentials:** `{"client_id": str, "client_secret": str}` (Reddit API)
- **source field:** `"reddit"`
- **Behavior:** Fetches recent posts. For link posts, `url` is the linked article; `content` is the post title + any self-text. For self posts, `content` is the full text. Comments are not ingested (too noisy for personality development).

### human_share

**The human-curated share channel.** Content the human explicitly shares via a dedicated Telegram bot chat, WhatsApp group, or similar single endpoint. This is the highest-signal source — every item represents an explicit attention choice by the human.

- **params:** `{"bot_chat_id": str}` — the dedicated chat/group where the human sends shares
- **credentials:** `{"bot_token": str}`
- **source field:** `"human_share"`
- **Behavior:**
  1. Polls the dedicated chat for new messages via toolkit/telegram_client.
  2. Each message is one share. Three message types:
     - **URL only**: extracts the URL, fetches the page content (HTTP + text extraction), uses fetched content as `content` and the URL as `url`.
     - **URL + text**: the text is stored as `human_annotation` (the human's comment on why this is interesting). Page content is fetched and used as `content`.
     - **Text only**: the message text becomes `content` directly. No URL fetch.
  3. `linked_urls` populated from any additional URLs in the message or the fetched page.
  4. For URL fetching: uses simple HTTP GET with text extraction (not full Playwright). Falls back to URL-only `ContentItem` (no `content`) if fetch fails — still valuable because the URL + annotation is signal.

**Why this adapter matters:** The design doc identifies the human's curated attention as high-signal data. The Twitter archive is described as "a decade of curated attention encoded as an associative network." The human_share adapter is the live, ongoing version of that — real-time curated attention feeding the personality development loop.

### Corpus Adapters

Corpus adapters handle bulk import of historical writing archives. They replace the former Seeding module — historical corpus enters through the same ingestion path as daily content. Each corpus adapter reads an archive format and produces `ContentItem` objects. During initial import, corpus adapter source labels should be listed in `AttentionFilterConfig.auto_accept_sources` so all corpus items enter Tier 1 with full annotation but without threshold filtering.

#### corpus_livejournal

Long-form reflective prose from LiveJournal HTML exports. Highest personality signal.

- **params:** `{"archive_path": str}` — path to exported HTML files or directory
- **source field:** `"corpus_livejournal"`
- **Extraction notes:** Recurring intellectual moves, characteristic tensions, associative patterns, negative space (what is avoided or treated with unusual care). Timestamps from post dates.

#### corpus_twitter

Twitter/X JSON archive. Mostly links with brief reactions.

- **params:** `{"archive_path": str}` — path to Twitter data export directory
- **source field:** `"corpus_twitter"`
- **Extraction notes:** Treat primarily as an exploratory library: the linked articles (where accessible) are the content; the tweets themselves are annotations. The pattern of *what was linked across time* is the associative network. Retweets without comment are lower-signal but still contribute to the attention map.

#### corpus_blog

Published blog posts in markdown or HTML.

- **params:** `{"archive_path": str, "format": str}` — format is `"markdown"` or `"html"`
- **source field:** `"corpus_blog"`
- **Extraction notes:** Similar to LiveJournal but more curated — may underrepresent characteristic frustrations visible in private writing. Titles and publication dates preserved.

#### corpus_conversations

Conversation history exports (e.g., Claude project exports, chat logs).

- **params:** `{"archive_path": str, "format": str}` — format is `"json"` or `"text"`
- **source field:** `"corpus_conversations"`
- **Extraction notes:** Recent, high-signal, unusually explicit about intellectual moves and preferences. The meta-analytical tendency (stepping back to examine conversation structure) is itself a characteristic move worth capturing.

#### corpus_text

Plain text files. No source-specific processing.

- **params:** `{"archive_path": str}`
- **source field:** `"corpus_text"`
- **Extraction notes:** Fragments extracted by paragraph or section boundary. No structural assumptions about content format.

## Integration with Attention Filter

Source Ingestion produces `ContentItem` objects. The Orchestrator passes them to `attention_filter.filter_content()`. The `source` field on each item determines whether the Attention Filter applies its acceptance threshold or auto-accepts.

The `auto_accept_sources` config on the Attention Filter controls this:

```python
# In AttentionFilterConfig (addition to ARCH_attention_filter.md):
auto_accept_sources: list[str] = field(default_factory=list)
# Sources that bypass acceptance_threshold but still get full annotation.
# Items from these sources always enter Tier 1 with importance, unresolvedness,
# friction_target, connections, and embedding computed normally.
# Default: empty (all sources filtered normally).
# Typical: ["human_share"] — human-curated content always accepted.
```

With `auto_accept_sources=["human_share"]`:
- Autonomous sources (telegram_channel, rss, reddit) go through the full filter with acceptance threshold
- Human-shared content is auto-accepted but still annotated — the system identifies friction, connections, and importance for everything the human shares
- The `human_annotation` field (the human's comment when sharing) is preserved in the `ContentItem` and available during annotation

## Inputs

- **External sources:** Telegram channels, RSS feeds, Reddit API, human messages to a Telegram bot
- **AdapterConfig** — per-adapter credentials, parameters, poll intervals
- **IngestionConfig** — global settings (timeouts, content length cap, link extraction)

## Outputs

- **ContentItem** — normalized content with source metadata. Passed to Attention Filter.
- **IngestionResult** — per-adapter batch result with error reporting.

**Downstream flow:**
```
SourceIngestion.poll() → list[ContentItem] → Orchestrator → AttentionFilter.filter_content() → Memory Store
```

## State

- **Last-seen markers:** per-adapter, tracks the most recent item processed (message_id, timestamp, or feed entry ID). Persisted to a JSON file in the Memory Store vault so polling survives restarts.
- No other state. Each adapter is stateless beyond its last-seen marker.

## Usage Example

```python
from source_ingestion import SourceIngestion, IngestionConfig, AdapterConfig
from attention_filter import AttentionFilter, AttentionFilterConfig
from memory_store import MemoryStore, NoteInput
from datetime import timedelta

store = MemoryStore(MemoryStoreConfig(vault_path="./memory"))
af = AttentionFilter(memory_store=store)

ingestion = SourceIngestion(IngestionConfig(
    adapters=[
        AdapterConfig(
            adapter_type="human_share",
            source_label="My shares",
            poll_interval=timedelta(minutes=5),  # check frequently — human shares are high priority
            credentials={"bot_token": "123:ABC..."},
            params={"bot_chat_id": "987654321"},
        ),
        AdapterConfig(
            adapter_type="telegram_channel",
            source_label="Philosophy channel",
            poll_interval=timedelta(hours=4),
            credentials={"bot_token": "123:ABC..."},
            params={"channel_username": "@philosophynow"},
        ),
        AdapterConfig(
            adapter_type="rss",
            source_label="Ribbonfarm",
            poll_interval=timedelta(hours=12),
            params={"feed_url": "https://www.ribbonfarm.com/feed/"},
        ),
    ],
))

# Poll all adapters
results = ingestion.poll()
all_items = [item for result in results for item in result.items]
print(f"Fetched {len(all_items)} items across {len(results)} adapters")

# Filter — human shares auto-accepted, everything else filtered normally
filter_config = AttentionFilterConfig(
    prompt_criteria=criteria,
    auto_accept_sources=["human_share"],
    llm_config=llm_config,
    embedding_config=embedding_config,
)
result = af.filter_content(all_items, filter_config)

# Store accepted fragments
for fragment in result.accepted:
    store.store_note(NoteInput(
        tier=1,
        content=fragment.content,
        title=fragment.annotation[:150],
        importance=fragment.importance_score,
        unresolvedness=fragment.unresolvedness,
        links=fragment.connections,
        tags=fragment.retention_criteria,
        source=fragment.source,
        friction_target=fragment.friction_target,
        embedding=fragment.embedding,
    ))
```
