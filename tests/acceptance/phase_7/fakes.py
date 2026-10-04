"""Fake browser / page objects for screenshot acceptance tests.

FakeBrowser and FakePage implement the BrowserLike / PageLike protocols
without Playwright.  Tests configure raise-on-method and HTTP status so every
branch of the capture logic can be exercised.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any


class FakeResponse:
    """Minimal navigation response with a status code."""

    def __init__(self, status: int) -> None:
        self.status = status


class FakePage:
    """Records all method calls; can be told to raise or return a status."""

    def __init__(
        self,
        *,
        goto_raises: Exception | None = None,
        goto_status: int | None = None,
        screenshot_raises: Exception | None = None,
        before_shot_raises: Exception | None = None,
        close_raises: Exception | None = None,
    ) -> None:
        self.goto_raises = goto_raises
        self.goto_status = goto_status
        self.screenshot_raises = screenshot_raises
        self.before_shot_raises = before_shot_raises
        self.close_raises = close_raises

        self.calls: list[tuple[str, Any]] = []

    def goto(self, url: str, *, wait_until: str, timeout: float) -> FakeResponse | None:
        self.calls.append(("goto", {"url": url, "wait_until": wait_until, "timeout": timeout}))
        if self.goto_raises is not None:
            raise self.goto_raises
        if self.goto_status is not None:
            return FakeResponse(self.goto_status)
        return None

    def wait_for_timeout(self, timeout: float) -> None:
        self.calls.append(("wait_for_timeout", {"timeout": timeout}))

    def screenshot(self, *, path: str, full_page: bool) -> None:
        self.calls.append(("screenshot", {"path": path, "full_page": full_page}))
        if self.screenshot_raises is not None:
            raise self.screenshot_raises
        # Write a minimal placeholder so file-existence checks pass.
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG\r\n\x1a\n")

    def close(self) -> None:
        self.calls.append(("close", {}))
        if self.close_raises is not None:
            raise self.close_raises

    # Convenience helpers for assertions
    def call_names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def kwargs_for(self, method: str) -> dict[str, Any]:
        for name, kw in self.calls:
            if name == method:
                return kw
        raise KeyError(f"no call to {method!r}")


class FakeBrowser:
    """One browser instance; each new_page() call returns a FakePage."""

    def __init__(self, pages: list[FakePage] | None = None) -> None:
        # If pages is given, they are handed out in order; otherwise blank pages.
        self._pages = list(pages) if pages else []
        self._page_index = 0
        self.new_page_calls: list[dict[str, Any]] = []
        self.closed = False

    def new_page(self, *, viewport: dict[str, int], color_scheme: str | None) -> FakePage:
        self.new_page_calls.append({"viewport": viewport, "color_scheme": color_scheme})
        if self._page_index < len(self._pages):
            page = self._pages[self._page_index]
        else:
            page = FakePage()
        self._page_index += 1
        return page

    def close(self) -> None:
        self.closed = True


@contextmanager
def make_factory(browser: FakeBrowser):
    """Context-manager factory that yields the given FakeBrowser."""
    yield browser
