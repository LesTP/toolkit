"""Failure isolation, exact diagnostics, ordering, and cleanup coverage."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from toolkit.screenshot import ShotSpec, capture, capture_many
from tests.screenshot.fakes import FakeBrowser, FakePage


@contextmanager
def factory(browser):
    yield browser


@pytest.mark.parametrize("failure, strict, expected", [
    ("navigation", False, None),
    ("navigation", True, "navigation: broken"),
    ("http", False, None),
    ("http", True, "http 503"),
    ("hook", False, "before_shot: ValueError: broken"),
    ("screenshot", False, "screenshot: broken"),
    ("settle", False, "settle: broken"),
    ("directory", False, "screenshot: blocked"),
])
def test_failures_preserve_invariant_and_continue(tmp_path, failure, strict, expected):
    page = FakePage(close_raises=RuntimeError("cleanup"))
    hook = None
    if failure == "navigation":
        page.goto_raises = RuntimeError("broken")
    elif failure == "http":
        page.goto_status = 503
    elif failure == "hook":
        def hook(page):
            raise ValueError("broken")
    elif failure == "screenshot":
        page.screenshot_raises = RuntimeError("broken")
    elif failure == "settle":
        def wait(timeout):
            raise RuntimeError("broken")
        page.wait_for_timeout = wait
    browser = FakeBrowser([page, FakePage()])
    calls = []
    original_close = browser.close
    def close():
        calls.append("close")
        original_close()
    browser.close = close
    specs = [ShotSpec("https://example.com", tmp_path / "first.png",
                      strict=strict, before_shot=hook),
             ShotSpec("https://example.com", tmp_path / "second.png")]
    if failure == "directory":
        # Fail only the first parent-directory operation.
        from pathlib import Path
        original_mkdir = Path.mkdir
        def mkdir(path, *args, **kwargs):
            if not calls:
                calls.append("mkdir")
                raise OSError("blocked")
            return original_mkdir(path, *args, **kwargs)
        with patch.object(Path, "mkdir", mkdir):
            results = capture_many(specs, browser_factory=lambda: factory(browser))
    else:
        results = capture_many(specs, browser_factory=lambda: factory(browser))
    first, second = results
    assert first.error == expected
    assert first.ok == (first.path is not None) == (first.error is None)
    assert first.warnings[-1] == "close: cleanup"
    assert page.call_names()[-1] == "close"
    assert second.ok and second.path.exists()
    assert calls.count("close") == 1
    if failure in ("navigation", "http"):
        assert first.warnings[0] == ("navigation: broken" if failure == "navigation" else "http 503")


def test_page_creation_failure_does_not_stop_batch(tmp_path):
    browser = FakeBrowser()
    original = browser.new_page
    attempts = []
    def new_page(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise RuntimeError("no page")
        return original(**kwargs)
    browser.new_page = new_page
    specs = [ShotSpec("file:///page.html", tmp_path / f"{i}.png") for i in range(2)]
    results = capture_many(specs, browser_factory=lambda: factory(browser))
    assert results[0].error == "page: no page"
    assert not results[0].ok and results[0].path is None
    assert results[1].ok and browser.closed


def test_hook_receives_page_after_navigation_and_settle(tmp_path):
    page = FakePage()
    def hook(actual):
        assert actual is page
        assert page.call_names() == ["goto", "wait_for_timeout"]
    spec = ShotSpec("file:///page.html", tmp_path / "shot.png", before_shot=hook,
                    full_page=True, wait_until="load", timeout_ms=1234)
    result = capture(spec, browser_factory=lambda: factory(FakeBrowser([page])))
    assert result.ok
    assert page.kwargs_for("goto") == {"url": spec.url, "wait_until": "load", "timeout": 1234}
    assert page.kwargs_for("screenshot") == {"path": str(spec.out_path), "full_page": True}


def test_default_provider_closes_browser_exactly_once(tmp_path):
    browser = FakeBrowser()
    calls = []
    def close():
        calls.append("close")
    browser.close = close
    @contextmanager
    def sync_playwright():
        yield SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kwargs: browser))
    with patch.dict("sys.modules", {"playwright.sync_api": SimpleNamespace(sync_playwright=sync_playwright)}):
        assert capture(ShotSpec("file:///page.html", tmp_path / "shot.png")).ok
    assert calls == ["close"]


def test_empty_batch_never_enters_provider():
    def forbidden():
        pytest.fail("empty batch must not launch a browser")
    assert capture_many([], browser_factory=forbidden) == []
