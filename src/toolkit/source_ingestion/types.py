"""Dataclasses for the Source Ingestion public API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class ContentItem:
    content: str
    source: str
    timestamp: datetime
    url: str | None = None
    linked_urls: list[str] = field(default_factory=list)
    title: str | None = None
    author: str | None = None
    human_annotation: str | None = None


@dataclass
class AdapterConfig:
    adapter_type: str
    source_label: str
    poll_interval: timedelta = timedelta(hours=4)
    enabled: bool = True
    credentials: dict | None = None
    params: dict = field(default_factory=dict)


@dataclass
class IngestionConfig:
    adapters: list[AdapterConfig]
    fetch_timeout: timedelta = timedelta(seconds=30)
    max_content_length: int = 50_000
    extract_links: bool = True


@dataclass
class IngestionResult:
    items: list[ContentItem]
    adapter_label: str
    errors: list[IngestionError]
    poll_timestamp: datetime


@dataclass
class IngestionError:
    url: str | None
    error: str
    adapter_label: str
