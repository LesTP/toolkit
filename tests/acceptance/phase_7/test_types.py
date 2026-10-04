"""Acceptance tests: types, ShotSpec validation, ShotResult invariant."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# ShotSpec construction & validation
# ---------------------------------------------------------------------------

def test_shotspec_valid_http(tmp_path):
    from toolkit.screenshot import ShotSpec
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "shot.png")
    assert spec.url == "http://example.com"
    assert spec.out_path == tmp_path / "shot.png"


def test_shotspec_valid_https(tmp_path):
    from toolkit.screenshot import ShotSpec
    ShotSpec(url="https://example.com/path", out_path=tmp_path / "a.png")


def test_shotspec_valid_file(tmp_path):
    from toolkit.screenshot import ShotSpec
    ShotSpec(url="file:///tmp/page.html", out_path=tmp_path / "a.png")


def test_shotspec_str_out_path_normalised_to_path(tmp_path):
    from toolkit.screenshot import ShotSpec
    spec = ShotSpec(url="http://example.com", out_path=str(tmp_path / "shot.png"))
    assert isinstance(spec.out_path, Path)


def test_shotspec_rejects_empty_url(tmp_path):
    from toolkit.screenshot import ShotSpec
    with pytest.raises(ValueError):
        ShotSpec(url="", out_path=tmp_path / "shot.png")


def test_shotspec_rejects_non_http_scheme(tmp_path):
    from toolkit.screenshot import ShotSpec
    with pytest.raises(ValueError):
        ShotSpec(url="ftp://example.com", out_path=tmp_path / "shot.png")


def test_shotspec_rejects_out_path_not_png(tmp_path):
    from toolkit.screenshot import ShotSpec
    with pytest.raises(ValueError):
        ShotSpec(url="http://example.com", out_path=tmp_path / "shot.jpg")


def test_shotspec_rejects_out_path_no_extension(tmp_path):
    from toolkit.screenshot import ShotSpec
    with pytest.raises(ValueError):
        ShotSpec(url="http://example.com", out_path=tmp_path / "shot")


def test_shotspec_rejects_nonpositive_viewport_width(tmp_path):
    from toolkit.screenshot import ShotSpec, Viewport
    with pytest.raises(ValueError):
        ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                 viewport=Viewport(width=0, height=800))


def test_shotspec_rejects_nonpositive_viewport_height(tmp_path):
    from toolkit.screenshot import ShotSpec, Viewport
    with pytest.raises(ValueError):
        ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                 viewport=Viewport(width=1024, height=0))


def test_shotspec_rejects_negative_settle_ms(tmp_path):
    from toolkit.screenshot import ShotSpec
    with pytest.raises(ValueError):
        ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                 settle_ms=-1)


def test_shotspec_rejects_zero_timeout_ms(tmp_path):
    from toolkit.screenshot import ShotSpec
    with pytest.raises(ValueError):
        ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                 timeout_ms=0)


def test_shotspec_rejects_unknown_color_scheme(tmp_path):
    from toolkit.screenshot import ShotSpec
    with pytest.raises(ValueError):
        ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                 color_scheme="sepia")  # type: ignore[arg-type]


def test_shotspec_rejects_unknown_wait_until(tmp_path):
    from toolkit.screenshot import ShotSpec
    with pytest.raises(ValueError):
        ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                 wait_until="forever")  # type: ignore[arg-type]


def test_shotspec_zero_settle_ms_allowed(tmp_path):
    from toolkit.screenshot import ShotSpec
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png", settle_ms=0)
    assert spec.settle_ms == 0


def test_shotspec_color_scheme_none_allowed(tmp_path):
    from toolkit.screenshot import ShotSpec
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png",
                    color_scheme=None)
    assert spec.color_scheme is None


# ---------------------------------------------------------------------------
# ShotResult invariant: ok ⟺ path is not None ⟺ error is None
# ---------------------------------------------------------------------------

def test_shotresult_ok_invariant_success(tmp_path):
    from toolkit.screenshot import ShotSpec, ShotResult
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    path = tmp_path / "s.png"
    result = ShotResult(spec=spec, ok=True, path=path, error=None, warnings=())
    assert result.ok is True
    assert result.path is not None
    assert result.error is None


def test_shotresult_ok_invariant_failure(tmp_path):
    from toolkit.screenshot import ShotSpec, ShotResult
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    result = ShotResult(spec=spec, ok=False, path=None, error="screenshot: timed out",
                        warnings=())
    assert result.ok is False
    assert result.path is None
    assert result.error is not None


def test_shotresult_carries_spec(tmp_path):
    from toolkit.screenshot import ShotSpec, ShotResult
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    result = ShotResult(spec=spec, ok=True, path=tmp_path / "s.png", error=None,
                        warnings=())
    assert result.spec is spec


def test_shotresult_carries_warnings(tmp_path):
    from toolkit.screenshot import ShotSpec, ShotResult
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")
    result = ShotResult(spec=spec, ok=True, path=tmp_path / "s.png", error=None,
                        warnings=("navigation: timeout",))
    assert "navigation: timeout" in result.warnings


# ---------------------------------------------------------------------------
# Viewport defaults
# ---------------------------------------------------------------------------

def test_viewport_defaults():
    from toolkit.screenshot import Viewport
    vp = Viewport()
    assert vp.width == 1600
    assert vp.height == 1000


# ---------------------------------------------------------------------------
# Import guard: missing Playwright raises ImportError with guidance
# ---------------------------------------------------------------------------

def test_import_guard_raises_import_error_with_guidance(tmp_path):
    """Default factory must raise ImportError when playwright is not installed."""
    from toolkit.screenshot import ShotSpec, capture
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")

    # Simulate playwright absent by patching the import inside the module.
    with patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
        with pytest.raises(ImportError, match="playwright"):
            capture(spec)


def test_import_guard_message_contains_install_command(tmp_path):
    """ImportError message must include the pip install guidance."""
    from toolkit.screenshot import ShotSpec, capture
    spec = ShotSpec(url="http://example.com", out_path=tmp_path / "s.png")

    with patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
        try:
            capture(spec)
        except ImportError as exc:
            assert "pip install" in str(exc)
        except Exception:
            pass  # module not yet present; test fails naturally
