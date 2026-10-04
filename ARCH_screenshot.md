# ARCH: Screenshot

## Purpose

Headless page capture for agents that need to *see* a web UI they built.
Given a URL (or a static build directory), render it in headless Chromium at
a chosen viewport and color scheme and write a PNG. Gives any worker backend
(Claude, Codex, pi.dev) "eyes" through a plain shell command, with no MCP or
editor integration required.

The module is deliberately generic: it navigates, waits, optionally runs a
consumer-supplied interaction hook, and captures. App-specific interaction
(click "Inspect", open a modal, toggle an in-app theme button) belongs to the
consumer via the `before_shot` hook — it is never encoded here.

**Provenance:** Ported from `p:\shared\_screenshot-tool` (Node + Playwright,
2026-07-30, used to verify build-a-stew's UI). The generic core of
`shot.mjs` moves here in Python; the build-a-stew-specific scripts
(`verify.mjs`, `recipe.mjs`, `save.mjs`) stay consumer-side as `before_shot`
hooks.

**Second-consumer rule:** build-a-stew (existing usage), Marginalia
(`reference-corpus-template`, rendered reading views), and the i2c
dashboard's screenshot-verification rule (D-dash-10).

## Public API

### capture

```python
def capture(
    spec: ShotSpec,
    *,
    browser_factory: BrowserFactory | None = None,
) -> ShotResult
```

- **Parameters:** `spec` — what to capture (see Types). `browser_factory` —
  injectable browser provider; `None` uses the default Playwright Chromium
  factory (lazy-imports `playwright.sync_api`).
- **Returns:** `ShotResult`. Never raises for page-level problems
  (navigation errors, HTTP error status, hook failure, screenshot failure):
  those are reported in `ShotResult.ok` / `error` / `warnings`.
- **Errors:** raises `ImportError` (with install guidance — see Dependencies)
  only when `browser_factory is None` and Playwright is not installed.
  Raises `ValueError` from `ShotSpec` construction for invalid specs.
- Equivalent to `capture_many([spec], browser_factory=...)[0]`.

### capture_many

```python
def capture_many(
    specs: Sequence[ShotSpec],
    *,
    browser_factory: BrowserFactory | None = None,
) -> list[ShotResult]
```

- Captures every spec using **one** browser instance (launched once, closed
  once — including when a capture fails). Results are returned in input
  order, one per spec. One spec failing does not stop the others.
- Each spec gets a fresh page (its own viewport + color scheme); the page is
  closed after capture.
- Empty `specs` → returns `[]` without launching a browser.

### static_server

```python
@contextmanager
def static_server(
    root: str | Path,
    *,
    mount: str = "/",
    host: str = "127.0.0.1",
    port: int = 0,
) -> Iterator[str]
```

- Serves the directory `root` over HTTP (stdlib `http.server`, background
  thread) for the duration of the `with` block. Yields the base URL
  including the mount prefix, always ending in `/`
  (e.g. `http://127.0.0.1:54321/build-a-stew/`).
- `mount` — URL path prefix under which `root` is served, for builds with a
  non-root base path (Vite `base: '/build-a-stew/'`). Requests outside the
  mount return 404.
- `port=0` picks a free ephemeral port. Binds `127.0.0.1` by default; the
  server is never exposed beyond loopback unless the caller passes `host`.
- Shuts the server down and joins the thread on exit, including on
  exception.
- **Errors:** `FileNotFoundError` if `root` is not an existing directory;
  `ValueError` if `mount` does not start with `/`.

### main (CLI)

```python
def main(argv: Sequence[str] | None = None) -> int
```

Invoked as `python -m toolkit.screenshot`:

```
python -m toolkit.screenshot URL --out PATH
    [--width 1600] [--height 1000]
    [--full-page]
    [--color-scheme light|dark|both]
    [--settle-ms 500] [--timeout-ms 30000]
    [--strict]
    [--serve DIR [--mount /prefix/]]
```

- `--color-scheme both` writes two files: `<stem>-light<suffix>` and
  `<stem>-dark<suffix>` derived from `--out` (e.g. `--out shots/home.png` →
  `shots/home-light.png`, `shots/home-dark.png`). Omitted → no emulation
  (browser default).
- `--serve DIR` starts `static_server(DIR, mount=...)` for the duration of
  the run; `URL` is then resolved relative to the served base URL
  (`URL` = `.` or `index.html` or `detail/`).
- Creates missing parent directories of `--out`.
- Prints each written file path on stdout, one per line; prints warnings
  and errors on stderr prefixed `warning:` / `error:`.
- **Exit codes:** `0` all captures ok; `1` at least one capture not ok;
  `2` usage error (argparse) or Playwright not installed (prints the install
  guidance from Dependencies).
- `main` accepts an injected `browser_factory` only through the Python API
  (tests call `run_cli(argv, browser_factory=...)`, a thin helper that
  `main` delegates to); the CLI itself always uses the default factory.

## Types

```python
ColorScheme = Literal["light", "dark"]

@dataclass(frozen=True)
class Viewport:
    width: int = 1600       # > 0
    height: int = 1000      # > 0

@dataclass(frozen=True)
class ShotSpec:
    url: str                                  # http(s):// or file:// URL
    out_path: Path                            # must end in ".png"
    viewport: Viewport = Viewport()
    full_page: bool = False
    color_scheme: ColorScheme | None = None   # None = no emulation
    wait_until: Literal["load", "domcontentloaded", "networkidle"] = "networkidle"
    settle_ms: int = 500                      # >= 0; extra wait after navigation
    timeout_ms: int = 30000                   # > 0; navigation timeout
    strict: bool = False                      # see Outputs
    before_shot: Callable[[PageLike], None] | None = None

@dataclass(frozen=True)
class ShotResult:
    spec: ShotSpec
    ok: bool
    path: Path | None          # set iff the PNG was written
    error: str | None          # set iff not ok
    warnings: tuple[str, ...]  # non-fatal issues, in occurrence order
```

`ShotSpec.__post_init__` validates and raises `ValueError` for: empty or
non-`http(s)`/`file` URL scheme, `out_path` not ending in `.png`
(case-insensitive), non-positive viewport dimensions, negative `settle_ms`,
non-positive `timeout_ms`, unknown `color_scheme` / `wait_until`. `out_path`
accepts `str` and is normalised to `Path`.

### Browser protocols (for injection and fakes)

```python
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
```

These mirror the subset of Playwright's sync API the module uses
(`Browser.new_page`, `Page.goto`, `Page.wait_for_timeout`,
`Page.screenshot`), so the default factory passes real Playwright objects
straight through. `goto` may return an object with an integer `status`
attribute (a Playwright `Response`) or `None`.

## Inputs

- A URL the headless browser can reach: `http(s)://` (live site or local
  server) or `file://` (single self-contained HTML, e.g. i2c's
  `dashboard.html`).
- Or a static build directory via `static_server` / `--serve`.
- Viewport, color scheme, full-page flag, timing, strictness per spec.
- Optional `before_shot(page)` hook — receives the live page after
  navigation + settle, before capture; it may click, fill, scroll, or wait.

## Outputs

One PNG per `ShotSpec` at `out_path` (parent directories created), plus a
`ShotResult`. Capture sequence per spec and how failures map to the result:

1. `new_page(viewport=..., color_scheme=...)` — exception → `ok=False`,
   `error="page: <msg>"`, no file.
2. `goto(url, wait_until=..., timeout=...)`:
   - raises → append warning `"navigation: <msg>"` and **continue to
     capture** (pages with long-polling or analytics often never reach
     `networkidle`; the original tool relied on this). With `strict=True` →
     `ok=False`, `error="navigation: <msg>"`, no capture.
   - returns a response with `status >= 400` → append warning
     `"http <status>"`; with `strict=True` → `ok=False`,
     `error="http <status>"`, no capture.
3. `wait_for_timeout(settle_ms)` (skipped when `settle_ms == 0`).
4. `before_shot(page)` if set — exception → `ok=False`,
   `error="before_shot: <ExceptionType>: <msg>"`, no capture.
5. `screenshot(path=str(out_path), full_page=...)` — exception → `ok=False`,
   `error="screenshot: <msg>"`; success → `ok=True`, `path=out_path`.
6. `page.close()` always runs; an exception there is appended as a warning,
   never changes `ok`.

Guarantee: `ok is True` ⇔ `path is not None` ⇔ `error is None`.

## State

None persistent. `capture_many` owns one browser for the duration of the
call; `static_server` owns one HTTP server thread for the duration of its
`with` block. Nothing is cached between calls.

## Usage Example

```python
from pathlib import Path
from toolkit.screenshot import ShotSpec, Viewport, capture_many, static_server

# Consumer-side hook: app-specific interaction stays in the consumer.
def open_first_detail(page):
    page.get_by_role("button", name="Inspect").first.click()
    page.wait_for_timeout(400)

with static_server("dist", mount="/build-a-stew/") as base:
    results = capture_many([
        ShotSpec(base, Path("shots/home-dark.png"), color_scheme="dark"),
        ShotSpec(base, Path("shots/home-light.png"), color_scheme="light"),
        ShotSpec(base, Path("shots/detail.png"), full_page=True,
                 before_shot=open_first_detail),
    ])

for r in results:
    print(r.path if r.ok else f"FAILED {r.spec.out_path}: {r.error}", *r.warnings)
```

Shell (any worker backend):

```bash
python -m toolkit.screenshot https://lestp.github.io/build-a-stew/ \
    --out shots/live.png --color-scheme both
python -m toolkit.screenshot . --serve dist --mount /build-a-stew/ \
    --out shots/local.png --full-page
```

## Phasing in This Pilot

Single phase (toolkit phase 7), five steps. All unit tests use an in-memory
fake browser (`tests/screenshot/fakes.py`: `FakeBrowser` / `FakePage` that
record calls and can be told to raise or return a status) — **no step's tests
may require Playwright or Chromium to be installed.**

- **Step 7.1** — package skeleton + types + import guard.
  `src/toolkit/screenshot/{__init__.py,types.py,_playwright.py}`;
  `Viewport`, `ShotSpec` (with `__post_init__` validation), `ShotResult`,
  `PageLike` / `BrowserLike` / `BrowserFactory` protocols; the default
  factory in `_playwright.py` lazy-imports `playwright.sync_api` and raises
  `ImportError` with the guidance text. Add the `screenshot = ["playwright>=1.47"]`
  extra to `pyproject.toml`. ~10 tests in `tests/screenshot/test_types.py`
  (each validation rule, str→Path normalisation, import guard via a
  monkeypatched import that raises `ImportError`).
- **Step 7.2** — `capture` / `capture_many` over the fake browser.
  Every branch of the Outputs sequence; one browser launch + close per
  `capture_many` call (closed even when a capture raises internally);
  per-spec fresh page with the spec's viewport/color scheme; input-order
  results; empty list launches nothing; parent dirs created; `strict`
  behaviour; the `ok`/`path`/`error` invariant. ~16 tests in
  `tests/screenshot/test_capture.py`.
- **Step 7.3** — `static_server`. Serves files under `mount`; 404 outside it;
  base URL ends in `/`; ephemeral port; shutdown on normal exit and on
  exception (port no longer accepting connections); `FileNotFoundError` /
  `ValueError` cases. Use `urllib.request` against the live loopback server.
  ~7 tests in `tests/screenshot/test_static_server.py`.
- **Step 7.4** — CLI (`__main__.py` + `run_cli`). Argument parsing and
  defaults; `--color-scheme both` file naming; `--serve`/`--mount` URL
  resolution; stdout paths / stderr `warning:`/`error:` lines; exit codes
  0/1/2 (Playwright-missing → 2 with guidance, simulated via the import
  guard). Drive through `run_cli(argv, browser_factory=fake)`. ~10 tests in
  `tests/screenshot/test_cli.py`.
- **Step 7.5** — live smoke test + docs. `tests/screenshot/test_live.py`:
  one test that renders a tiny `file://` HTML page (light/dark CSS via
  `prefers-color-scheme`) and asserts both PNGs exist and differ; it must
  `pytest.importorskip("playwright.sync_api")` and skip cleanly (not fail)
  when Chromium is not installed. Add the `toolkit.screenshot` section to
  `API.md` (bump `Last synced:`), the module row to the README module list
  if one exists, and the "Screenshot" bullet to the toolkit rule's
  "Available Modules" list in `CLAUDE.md`.

## Escalation Triggers

- **Playwright install required** — EXECUTE halts if making a step's tests
  pass appears to require installing Playwright or downloading Chromium
  into the container (the toolkit venv is read-only; see project gotchas).
  Unit tests must stay fake-backed. Recovery: operator installs
  `toolkit[screenshot]` + `python -m playwright install chromium`, or the
  step is reshaped to stay fake-backed.
- **Sync API inside an event loop** — PLAN or EXECUTE halts if a
  requirement surfaces to call `capture` from inside a running asyncio
  loop (Playwright's sync API raises there). An async variant is out of
  scope for this phase. Recovery: operator decides whether to add an async
  API in a later phase.
- **Consumer files touched** — EXECUTE halts if any step would modify files
  outside `p:\shared\toolkit` (e.g. build-a-stew, `_screenshot-tool`).
  Migrating consumers is separate work.

## Inputs the Screenshot Module Does Not Handle

- **App-specific interaction** (clicking an in-app theme toggle, opening a
  modal, filling a form) — owned by the consumer via `before_shot`.
- **Building or running dev servers** (Vite, webpack, `npm run dev`) — the
  consumer builds first; `static_server` only serves already-built files.
- **Visual comparison / regression testing** (pixel diffs, baselines) —
  out of scope; the module produces images, judgement is the caller's.
- **Browser installation** — the operator runs
  `python -m playwright install chromium` once per host.
- **Non-Chromium browsers, mobile device emulation, auth/cookies, video,
  PDF** — not in v1.
- **Async usage** — sync API only (see Escalation Triggers).

## Testing Strategy

- **Fake-backed unit tests** — all behaviour in Outputs is tested against
  `FakeBrowser`/`FakePage`, which record `new_page` / `goto` /
  `wait_for_timeout` / `screenshot` / `close` calls and arguments and can be
  configured to raise at any stage or to return a response status.
  `FakePage.screenshot` writes a small placeholder file at `path` so the
  file-exists assertions are real.
- **Loopback server tests** — `static_server` is tested for real on
  `127.0.0.1` (stdlib only, no browser).
- **Live smoke** — exactly one opt-in test that skips when Playwright or
  Chromium is unavailable.
- **Property** — for every `ShotResult`: `ok` ⇔ `path is not None` ⇔
  `error is None`; `capture_many` returns `len(specs)` results and closes
  the browser exactly once.

Run tests per the project gotchas (container venv + `PYTHONPATH=src`).

## Provisional Contracts

- **`before_shot` receives a raw Playwright `Page`** — typed as `PageLike`
  for the four methods the module calls, but consumers will use more of the
  Playwright API (`get_by_role`, `fill`). Will firm up if a second
  interaction-heavy consumer wants a toolkit-level helper set.
- **Theme handling via `prefers-color-scheme` emulation only** — apps whose
  theme is driven solely by an in-app toggle (build-a-stew today) need a
  `before_shot` hook to click it. Revisit if most consumers need toggles.

## Dependencies

- **Toolkit modules:** none (leaf).
- **External:** Playwright for Python (`playwright>=1.47`), lazy-imported
  only inside the default browser factory; installed via the optional extra
  `pip install toolkit[screenshot]`, plus a one-time
  `python -m playwright install chromium` per host. Import-guard message
  (verbatim):
  `toolkit.screenshot needs Playwright: pip install "toolkit[screenshot]" && python -m playwright install chromium`
- **Stdlib:** `http.server`, `threading`, `argparse`, `pathlib`,
  `contextlib`.
- Python 3.9+ — use `from __future__ import annotations`; no `match`.
