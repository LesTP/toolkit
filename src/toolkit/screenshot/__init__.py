"""Headless page capture with an optional Playwright browser provider."""
from .capture import capture, capture_many
from .cli import main, run_cli
from .server import static_server
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
    "ShotResult", "ShotSpec", "Viewport", "capture", "capture_many", "static_server", "main", "run_cli",
]
