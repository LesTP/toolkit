"""Shell entry point for synchronous page capture."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from pathlib import Path
import sys
from typing import Sequence
from urllib.parse import urljoin

from .capture import capture_many
from .server import static_server
from .types import BrowserFactory, ShotSpec, Viewport


def run_cli(
    argv: Sequence[str] | None = None, *,
    browser_factory: BrowserFactory | None = None,
) -> int:
    """Run the CLI, optionally using an injected browser for tests."""
    parser = argparse.ArgumentParser(prog="python -m toolkit.screenshot")
    parser.add_argument("url", metavar="URL")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--full-page", action="store_true")
    parser.add_argument("--color-scheme", choices=("light", "dark", "both"))
    parser.add_argument("--settle-ms", type=int, default=500)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--serve", type=Path, metavar="DIR")
    parser.add_argument("--mount", default="/")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        with ExitStack() as stack:
            url = args.url
            if args.serve is not None:
                base = stack.enter_context(static_server(args.serve, mount=args.mount))
                url = urljoin(base, url)
            schemes = ("light", "dark") if args.color_scheme == "both" else (args.color_scheme,)
            specs = []
            for scheme in schemes:
                out = args.out
                if args.color_scheme == "both":
                    out = out.with_name(f"{out.stem}-{scheme}{out.suffix}")
                specs.append(ShotSpec(
                    url, out, viewport=Viewport(args.width, args.height),
                    full_page=args.full_page, color_scheme=scheme,
                    settle_ms=args.settle_ms, timeout_ms=args.timeout_ms,
                    strict=args.strict,
                ))
            results = capture_many(specs, browser_factory=browser_factory)
    except (ValueError, FileNotFoundError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for result in results:
        if result.path is not None:
            print(result.path)
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if result.error is not None:
            print(f"error: {result.error}", file=sys.stderr)
    return 0 if all(result.ok for result in results) else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run with the default Playwright provider."""
    return run_cli(argv)
