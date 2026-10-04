"""Focused coverage for the screenshot package foundation."""
from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from toolkit.screenshot import ShotSpec, Viewport
from toolkit.screenshot._playwright import INSTALL_GUIDANCE, default_browser_factory


@pytest.mark.parametrize("overrides", [
    {"url": ""}, {"url": "ftp://example.com"}, {"out_path": "s.jpg"},
    {"viewport": Viewport(0, 1)}, {"viewport": Viewport(1, -1)},
    {"settle_ms": -1}, {"timeout_ms": 0}, {"color_scheme": "sepia"},
    {"wait_until": "forever"},
])
def test_invalid_spec(overrides):
    values = {"url": "https://example.com", "out_path": "s.png"}
    values.update(overrides)
    with pytest.raises(ValueError):
        ShotSpec(**values)


def test_path_normalisation_and_immutable_defaults():
    spec = ShotSpec("file:///page.html", "s.PNG")
    assert spec.out_path.name == "s.PNG"
    assert spec.viewport == Viewport(1600, 1000)
    with pytest.raises(FrozenInstanceError):
        spec.settle_ms = 0


def test_missing_playwright_guidance():
    with patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
        with pytest.raises(ImportError) as caught:
            with default_browser_factory():
                pytest.fail("missing dependency should prevent launching")
    assert str(caught.value) == INSTALL_GUIDANCE
    assert INSTALL_GUIDANCE == 'toolkit.screenshot needs Playwright: pip install "toolkit[screenshot]" && python -m playwright install chromium'


@pytest.mark.parametrize("fail", [False, True])
def test_browser_lifecycle_without_real_playwright(fail):
    calls = []
    browser = SimpleNamespace(close=lambda: calls.append("browser.close"))

    def launch(**kwargs):
        assert kwargs == {"headless": True}
        calls.append("launch")
        return browser

    @contextmanager
    def sync_playwright():
        calls.append("start")
        try:
            yield SimpleNamespace(chromium=SimpleNamespace(launch=launch))
        finally:
            calls.append("stop")

    fake = SimpleNamespace(sync_playwright=sync_playwright)
    with patch.dict(sys.modules, {"playwright.sync_api": fake}):
        try:
            with default_browser_factory() as actual:
                assert actual is browser
                if fail:
                    raise RuntimeError("consumer failed")
        except RuntimeError:
            assert fail
    assert calls == ["start", "launch", "browser.close", "stop"]
