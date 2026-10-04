"""Capture specifications, results, and injectable browser interfaces."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, ContextManager, Literal, Protocol
from urllib.parse import urlsplit

ColorScheme = Literal["light", "dark"]


class PageLike(Protocol):
    def goto(self, url: str, *, wait_until: str, timeout: float) -> Any: ...
    def wait_for_timeout(self, timeout: float) -> None: ...
    def screenshot(self, *, path: str, full_page: bool) -> Any: ...
    def close(self) -> None: ...


class BrowserLike(Protocol):
    def new_page(self, *, viewport: dict[str, int],
                 color_scheme: str | None) -> PageLike: ...
    def close(self) -> None: ...


BrowserFactory = Callable[[], ContextManager[BrowserLike]]


@dataclass(frozen=True)
class Viewport:
    width: int = 1600
    height: int = 1000


@dataclass(frozen=True)
class ShotSpec:
    url: str
    out_path: Path
    viewport: Viewport = Viewport()
    full_page: bool = False
    color_scheme: ColorScheme | None = None
    wait_until: Literal["load", "domcontentloaded", "networkidle"] = "networkidle"
    settle_ms: int = 500
    timeout_ms: int = 30000
    strict: bool = False
    before_shot: Callable[[PageLike], None] | None = None

    def __post_init__(self) -> None:
        if not self.url or urlsplit(self.url).scheme not in ("http", "https", "file"):
            raise ValueError("url must use an http, https, or file scheme")
        object.__setattr__(self, "out_path", Path(self.out_path))
        if self.out_path.suffix.lower() != ".png":
            raise ValueError("out_path must end in .png")
        if self.viewport.width <= 0 or self.viewport.height <= 0:
            raise ValueError("viewport dimensions must be positive")
        if self.settle_ms < 0:
            raise ValueError("settle_ms must be non-negative")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if self.color_scheme not in (None, "light", "dark"):
            raise ValueError("unknown color_scheme")
        if self.wait_until not in ("load", "domcontentloaded", "networkidle"):
            raise ValueError("unknown wait_until")


@dataclass(frozen=True)
class ShotResult:
    spec: ShotSpec
    ok: bool
    path: Path | None
    error: str | None
    warnings: tuple[str, ...]
