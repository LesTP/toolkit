"""Opt-in smoke coverage using an operator-installed Chromium."""
from __future__ import annotations

import os

import pytest

from toolkit.screenshot import ShotSpec, Viewport, capture_many


def test_live_light_and_dark_pngs(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    if os.environ.get("TOOLKIT_SCREENSHOT_LIVE") != "1":
        pytest.skip("Set TOOLKIT_SCREENSHOT_LIVE=1 to run the Chromium smoke test")

    html = tmp_path / "theme.html"
    html.write_text(
        "<!doctype html><style>html {background: white; color: black}"
        "@media (prefers-color-scheme: dark) {"
        "html {background: black; color: white}}</style><p>Screenshot smoke</p>",
        encoding="utf-8",
    )
    specs = [
        ShotSpec(html.as_uri(), tmp_path / f"{scheme}.png",
                 viewport=Viewport(320, 200), color_scheme=scheme,
                 wait_until="load", settle_ms=0, strict=True)
        for scheme in ("light", "dark")
    ]
    try:
        results = capture_many(specs)
    except playwright.Error as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip("Chromium is not installed; run python -m playwright install chromium")
        raise

    assert len(results) == 2
    for result in results:
        assert result.ok, result.error
        assert result.path == result.spec.out_path
        assert result.error is None
        assert result.path.is_file()
        assert result.path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert results[0].path.read_bytes() != results[1].path.read_bytes()
