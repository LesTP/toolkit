"""Synchronous captures with isolated pages and recoverable page errors."""
from __future__ import annotations

from typing import Sequence

from ._playwright import default_browser_factory
from .types import BrowserFactory, BrowserLike, ShotResult, ShotSpec


def _capture(browser: BrowserLike, spec: ShotSpec) -> ShotResult:
    warnings: list[str] = []
    error = None
    path = None
    try:
        page = browser.new_page(
            viewport={"width": spec.viewport.width, "height": spec.viewport.height},
            color_scheme=spec.color_scheme,
        )
    except Exception as exc:
        return ShotResult(spec, False, None, f"page: {exc}", ())

    try:
        try:
            response = page.goto(spec.url, wait_until=spec.wait_until,
                                 timeout=spec.timeout_ms)
        except Exception as exc:
            warning = f"navigation: {exc}"
            warnings.append(warning)
            if spec.strict:
                error = warning
        else:
            status = getattr(response, "status", None)
            if isinstance(status, int) and status >= 400:
                warning = f"http {status}"
                warnings.append(warning)
                if spec.strict:
                    error = warning

        if error is None and spec.settle_ms:
            try:
                page.wait_for_timeout(spec.settle_ms)
            except Exception as exc:
                error = f"settle: {exc}"

        if error is None and spec.before_shot is not None:
            try:
                spec.before_shot(page)
            except Exception as exc:
                error = f"before_shot: {type(exc).__name__}: {exc}"

        if error is None:
            try:
                spec.out_path.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(spec.out_path), full_page=spec.full_page)
            except Exception as exc:
                error = f"screenshot: {exc}"
            else:
                path = spec.out_path
    finally:
        try:
            page.close()
        except Exception as exc:
            warnings.append(f"close: {exc}")

    return ShotResult(spec, error is None, path, error, tuple(warnings))


def capture_many(
    specs: Sequence[ShotSpec], *, browser_factory: BrowserFactory | None = None,
) -> list[ShotResult]:
    """Capture in input order, sharing one browser and closing each fresh page.

    The default provider owns browser cleanup. For injected providers we close
    the browser before leaving their context, even when a capture fails.
    """
    if not specs:
        return []
    factory = default_browser_factory if browser_factory is None else browser_factory
    with factory() as browser:
        try:
            return [_capture(browser, spec) for spec in specs]
        finally:
            if browser_factory is not None:
                browser.close()


def capture(
    spec: ShotSpec, *, browser_factory: BrowserFactory | None = None,
) -> ShotResult:
    """Capture a single specification; equivalent to capture_many([spec])[0]."""
    return capture_many([spec], browser_factory=browser_factory)[0]
