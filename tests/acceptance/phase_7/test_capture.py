"""Acceptance tests: capture / capture_many behavior."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.acceptance.phase_7.fakes import FakeBrowser, FakePage, make_factory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _factory(browser: FakeBrowser):
    """Return a zero-arg callable that is a context-manager factory."""
    @contextmanager
    def _inner():
        yield browser
    return _inner


# ---------------------------------------------------------------------------
# capture() is equivalent to capture_many([spec])[0]
# ---------------------------------------------------------------------------

def test_capture_returns_single_result(tmp_path):
    from toolkit.screenshot import ShotSpec, capture
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    browser = FakeBrowser()
    result = capture(spec, browser_factory=_factory(browser))
    assert result.spec is spec


def test_capture_equivalent_to_capture_many(tmp_path):
    from toolkit.screenshot import ShotSpec, capture, capture_many
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "a.png")
    browser1 = FakeBrowser()
    browser2 = FakeBrowser()
    r1 = capture(spec, browser_factory=_factory(browser1))
    spec2 = ShotSpec(url="http://example.com", out_path=tmp_path / "b.png")
    r2 = capture_many([spec2], browser_factory=_factory(browser2))[0]
    assert r1.ok == r2.ok


# ---------------------------------------------------------------------------
# Successful capture
# ---------------------------------------------------------------------------

def test_successful_capture_ok_true(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    browser = FakeBrowser()
    results = capture_many([spec], browser_factory=_factory(browser))
    assert results[0].ok is True


def test_successful_capture_path_set(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    browser = FakeBrowser()
    results = capture_many([spec], browser_factory=_factory(browser))
    assert results[0].path == tmp_path / "s.png"


def test_successful_capture_error_none(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    browser = FakeBrowser()
    results = capture_many([spec], browser_factory=_factory(browser))
    assert results[0].error is None


def test_successful_capture_file_written(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    browser = FakeBrowser()
    capture_many([spec], browser_factory=_factory(browser))
    assert (tmp_path / "s.png").exists()


# ---------------------------------------------------------------------------
# Parent directories are created
# ---------------------------------------------------------------------------

def test_parent_dirs_created(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    out = tmp_path / "deep" / "nested" / "shot.png"
    spec = ShotSpec(url="http://example.com", out_path=out)
    browser = FakeBrowser()
    results = capture_many([spec], browser_factory=_factory(browser))
    assert results[0].ok is True
    assert out.exists()


# ---------------------------------------------------------------------------
# Browser lifecycle: one launch + one close per capture_many call
# ---------------------------------------------------------------------------

def test_one_browser_per_capture_many(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    specs = [
        ShotSpec(url="http://example.com", out_path=tmp_path / "a.png"),
        ShotSpec(url="http://example.com", out_path=tmp_path / "b.png"),
    ]
    browser = FakeBrowser()
    capture_many(specs, browser_factory=_factory(browser))
    # Exactly two pages were created (one per spec), not two browser launches.
    assert len(browser.new_page_calls) == 2


def test_browser_closed_after_capture_many(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    browser = FakeBrowser()
    capture_many([spec], browser_factory=_factory(browser))
    assert browser.closed is True


def test_browser_closed_even_when_capture_fails(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(screenshot_raises=RuntimeError("disk full"))
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    capture_many([spec], browser_factory=_factory(browser))
    assert browser.closed is True


# ---------------------------------------------------------------------------
# Empty spec list
# ---------------------------------------------------------------------------

def test_empty_specs_returns_empty_list(tmp_path):
    from toolkit.screenshot import capture_many
    browser = FakeBrowser()
    results = capture_many([], browser_factory=_factory(browser))
    assert results == []


def test_empty_specs_no_browser_launched():
    from toolkit.screenshot import capture_many
    browser = FakeBrowser()
    capture_many([], browser_factory=_factory(browser))
    assert not browser.closed  # close was never called


# ---------------------------------------------------------------------------
# Per-spec fresh page with correct viewport and color_scheme
# ---------------------------------------------------------------------------

def test_page_receives_correct_viewport(tmp_path):
    from toolkit.screenshot import ShotSpec, Viewport, capture_many
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    viewport=Viewport(width=1280, height=720))
    browser = FakeBrowser()
    capture_many([spec], browser_factory=_factory(browser))
    vp = browser.new_page_calls[0]["viewport"]
    assert vp["width"] == 1280
    assert vp["height"] == 720


def test_page_receives_color_scheme(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    color_scheme="dark")
    browser = FakeBrowser()
    capture_many([spec], browser_factory=_factory(browser))
    assert browser.new_page_calls[0]["color_scheme"] == "dark"


def test_page_receives_none_color_scheme(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    color_scheme=None)
    browser = FakeBrowser()
    capture_many([spec], browser_factory=_factory(browser))
    assert browser.new_page_calls[0]["color_scheme"] is None


# ---------------------------------------------------------------------------
# Results in input order
# ---------------------------------------------------------------------------

def test_results_in_input_order(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    specs = [
        ShotSpec(url="http://example.com/1", out_path=tmp_path / "a.png"),
        ShotSpec(url="http://example.com/2", out_path=tmp_path / "b.png"),
        ShotSpec(url="http://example.com/3", out_path=tmp_path / "c.png"),
    ]
    browser = FakeBrowser()
    results = capture_many(specs, browser_factory=_factory(browser))
    assert len(results) == 3
    for spec, result in zip(specs, results):
        assert result.spec is spec


# ---------------------------------------------------------------------------
# settle_ms behaviour
# ---------------------------------------------------------------------------

def test_settle_ms_zero_skips_wait(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage()
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    settle_ms=0)
    capture_many([spec], browser_factory=_factory(browser))
    assert "wait_for_timeout" not in page.call_names()


def test_settle_ms_positive_calls_wait(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage()
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    settle_ms=250)
    capture_many([spec], browser_factory=_factory(browser))
    assert "wait_for_timeout" in page.call_names()
    assert page.kwargs_for("wait_for_timeout")["timeout"] == 250


# ---------------------------------------------------------------------------
# Strict=False: navigation exception → warning, capture continues
# ---------------------------------------------------------------------------

def test_navigation_raises_nonstrict_adds_warning(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(goto_raises=TimeoutError("took too long"))
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    strict=False)
    results = capture_many([spec], browser_factory=_factory(browser))
    assert any("navigation" in w for w in results[0].warnings)


def test_navigation_raises_nonstrict_capture_continues(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(goto_raises=TimeoutError("took too long"))
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    strict=False)
    results = capture_many([spec], browser_factory=_factory(browser))
    # screenshot was attempted (ok=True) or at least no navigation error stops it
    assert "screenshot" in page.call_names()


# ---------------------------------------------------------------------------
# Strict=True: navigation exception → ok=False, no capture
# ---------------------------------------------------------------------------

def test_navigation_raises_strict_ok_false(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(goto_raises=TimeoutError("took too long"))
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    strict=True)
    results = capture_many([spec], browser_factory=_factory(browser))
    assert results[0].ok is False


def test_navigation_raises_strict_error_set(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(goto_raises=TimeoutError("took too long"))
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    strict=True)
    results = capture_many([spec], browser_factory=_factory(browser))
    assert results[0].error is not None
    assert "navigation" in results[0].error


def test_navigation_raises_strict_no_screenshot_called(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(goto_raises=TimeoutError("took too long"))
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    strict=True)
    capture_many([spec], browser_factory=_factory(browser))
    assert "screenshot" not in page.call_names()


# ---------------------------------------------------------------------------
# HTTP status >= 400
# ---------------------------------------------------------------------------

def test_http_error_status_nonstrict_adds_warning(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(goto_status=404)
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    strict=False)
    results = capture_many([spec], browser_factory=_factory(browser))
    assert any("http" in w and "404" in w for w in results[0].warnings)


def test_http_error_status_strict_ok_false(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(goto_status=500)
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    strict=True)
    results = capture_many([spec], browser_factory=_factory(browser))
    assert results[0].ok is False
    assert results[0].error is not None


def test_http_ok_status_no_warning(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(goto_status=200)
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    results = capture_many([spec], browser_factory=_factory(browser))
    assert results[0].ok is True
    assert not results[0].warnings


# ---------------------------------------------------------------------------
# before_shot hook
# ---------------------------------------------------------------------------

def test_before_shot_exception_ok_false(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many

    def bad_hook(page):
        raise ValueError("hook error")

    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    before_shot=bad_hook)
    browser = FakeBrowser()
    results = capture_many([spec], browser_factory=_factory(browser))
    assert results[0].ok is False


def test_before_shot_exception_error_message(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many

    def bad_hook(page):
        raise ValueError("hook error")

    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    before_shot=bad_hook)
    browser = FakeBrowser()
    results = capture_many([spec], browser_factory=_factory(browser))
    assert "before_shot" in results[0].error
    assert "ValueError" in results[0].error


def test_before_shot_exception_no_screenshot(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many

    def bad_hook(page):
        raise RuntimeError("boom")

    page = FakePage()
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    before_shot=bad_hook)
    capture_many([spec], browser_factory=_factory(browser))
    assert "screenshot" not in page.call_names()


def test_before_shot_called_before_screenshot(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    call_order = []

    def hook(page):
        call_order.append("hook")

    page = FakePage()
    original_screenshot = page.screenshot
    def recording_screenshot(**kw):
        call_order.append("screenshot")
        original_screenshot(**kw)
    page.screenshot = recording_screenshot  # type: ignore[method-assign]

    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    before_shot=hook)
    capture_many([spec], browser_factory=_factory(browser))
    assert call_order == ["hook", "screenshot"]


# ---------------------------------------------------------------------------
# screenshot exception
# ---------------------------------------------------------------------------

def test_screenshot_exception_ok_false(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(screenshot_raises=OSError("disk full"))
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    results = capture_many([spec], browser_factory=_factory(browser))
    assert results[0].ok is False
    assert "screenshot" in results[0].error


# ---------------------------------------------------------------------------
# One spec failing does not stop others
# ---------------------------------------------------------------------------

def test_one_failure_does_not_stop_remaining(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    failing_page = FakePage(screenshot_raises=RuntimeError("oops"))
    ok_page = FakePage()
    browser = FakeBrowser(pages=[failing_page, ok_page])
    specs = [
        ShotSpec(url="http://example.com", out_path=tmp_path / "fail.png"),
        ShotSpec(url="http://example.com", out_path=tmp_path / "ok.png"),
    ]
    results = capture_many(specs, browser_factory=_factory(browser))
    assert results[0].ok is False
    assert results[1].ok is True


# ---------------------------------------------------------------------------
# page.close() always called
# ---------------------------------------------------------------------------

def test_page_close_called_on_success(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage()
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    capture_many([spec], browser_factory=_factory(browser))
    assert "close" in page.call_names()


def test_page_close_called_on_failure(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(screenshot_raises=RuntimeError("fail"))
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    capture_many([spec], browser_factory=_factory(browser))
    assert "close" in page.call_names()


def test_page_close_exception_becomes_warning(tmp_path):
    from toolkit.screenshot import ShotSpec, capture_many
    page = FakePage(close_raises=RuntimeError("close failed"))
    browser = FakeBrowser(pages=[page])
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    results = capture_many([spec], browser_factory=_factory(browser))
    # page.close() raised but ok should still be True (screenshot succeeded)
    assert results[0].ok is True
    assert results[0].warnings  # close error promoted to warning
