"""Headless page capture with an optional Playwright browser provider."""
from .capture import capture, capture_many
from .types import (
    BrowserFactory,
    BrowserLike,
    ColorScheme,
    PageLike,
    ShotResult,
    ShotSpec,
    Viewport,
)

__all__ = [
    "BrowserFactory", "BrowserLike", "ColorScheme", "PageLike",
    "ShotResult", "ShotSpec", "Viewport", "capture", "capture_many",
]
