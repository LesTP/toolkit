"""Dataclasses for the Gateway public API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class GatewayConfig:
    platforms: list[PlatformConfig]
    default_platform: str
    listen: bool = True


@dataclass
class PlatformConfig:
    name: str
    adapter_type: str
    credentials: dict
    params: dict = field(default_factory=dict)
    enabled: bool = True
    output_formats: list[str] = field(default_factory=lambda: ["text"])


@dataclass
class InboundMessage:
    content: str
    platform: str
    message_id: str
    sender: str
    timestamp: datetime
    reply_to: str | None = None
    reactions: list[str] | None = None
    raw: dict | None = None


@dataclass
class OutboundMessage:
    content: str
    platform: str
    format: str = "text"
    reply_to: str | None = None
    intent_tag: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class DeliveryResult:
    success: bool
    platform: str
    message_id: str | None
    error: str | None = None


@dataclass(kw_only=True)
class FeedbackSignal:
    platform: str
    message_id: str
    signal_type: str
    value: str | None = None
    sender: str
    timestamp: datetime
