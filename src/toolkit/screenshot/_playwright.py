"""Lazy optional Playwright provider."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .types import BrowserLike

INSTALL_GUIDANCE = 'toolkit.screenshot needs Playwright: pip install "toolkit[screenshot]" && python -m playwright install chromium'


@contextmanager
def default_browser_factory() -> Iterator[BrowserLike]:
    """Launch Chromium and release it before stopping Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(INSTALL_GUIDANCE) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()
