"""Focused fake-backed checks for CLI arguments and diagnostics."""
from __future__ import annotations

import sys
from urllib.parse import urlsplit
from urllib.request import urlopen

import pytest

from toolkit.screenshot import main, run_cli
from toolkit.screenshot._playwright import INSTALL_GUIDANCE
from tests.screenshot.fakes import FakeBrowser, FakePage, make_factory


def test_defaults(tmp_path, capsys):
    page = FakePage()
    browser = FakeBrowser([page])
    out = tmp_path / 'shot.png'
    assert run_cli(['https://example.com', '--out', str(out)],
                   browser_factory=lambda: make_factory(browser)) == 0
    assert browser.new_page_calls == [
        {'viewport': {'width': 1600, 'height': 1000}, 'color_scheme': None}]
    assert page.kwargs_for('goto') == {
        'url': 'https://example.com', 'wait_until': 'networkidle', 'timeout': 30000}
    assert page.kwargs_for('wait_for_timeout') == {'timeout': 500}
    assert page.kwargs_for('screenshot') == {'path': str(out), 'full_page': False}
    assert capsys.readouterr().out == f'{out}\n'


def test_flags_and_both_preserve_suffix(tmp_path, capsys):
    pages = [FakePage(), FakePage()]
    browser = FakeBrowser(pages)
    out = tmp_path / 'home.preview.PNG'
    assert run_cli(['file:///tmp/page.html', '--out', str(out),
                    '--color-scheme', 'both', '--width', '800', '--height', '600',
                    '--full-page', '--settle-ms', '0', '--timeout-ms', '123'],
                   browser_factory=lambda: make_factory(browser)) == 0
    paths = [tmp_path / f'home.preview-{scheme}.PNG' for scheme in ('light', 'dark')]
    assert capsys.readouterr().out.splitlines() == [str(p) for p in paths]
    assert all(p.exists() for p in paths)
    assert [c['color_scheme'] for c in browser.new_page_calls] == ['light', 'dark']
    for page in pages:
        assert page.kwargs_for('goto')['timeout'] == 123
        assert 'wait_for_timeout' not in page.call_names()
        assert page.kwargs_for('screenshot')['full_page'] is True
    assert browser.new_page_calls[0]['viewport'] == {'width': 800, 'height': 600}


def test_partial_failure_diagnostics(tmp_path, capsys):
    browser = FakeBrowser([FakePage(goto_status=503),
                           FakePage(screenshot_raises=RuntimeError('disk full'))])
    assert run_cli(['https://example.com', '--out', str(tmp_path / 'shot.png'),
                    '--color-scheme', 'both'],
                   browser_factory=lambda: make_factory(browser)) == 1
    output = capsys.readouterr()
    assert output.out == f'{tmp_path / "shot-light.png"}\n'
    assert output.err == 'warning: http 503\nerror: screenshot: disk full\n'
    assert browser.closed


@pytest.mark.parametrize('extra', [[], ['--width', '0'], ['--height', '-1'],
                                  ['--settle-ms', '-1'], ['--timeout-ms', '0'],
                                  ['--color-scheme', 'blue']])
def test_usage_errors_do_not_launch(tmp_path, capsys, extra):
    def unexpected_factory():
        pytest.fail('invalid arguments launched a browser')
    argv = ['https://example.com']
    if extra:
        argv += ['--out', str(tmp_path / 'shot.png')] + extra
    assert run_cli(argv, browser_factory=unexpected_factory) == 2
    assert capsys.readouterr().err


def test_missing_playwright_guidance(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, 'playwright', None)
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', None)
    assert main(['https://example.com', '--out', str(tmp_path / 'shot.png')]) == 2
    assert capsys.readouterr().err == f'error: {INSTALL_GUIDANCE}\n'


@pytest.mark.parametrize('relative', ['.', 'index.html', 'detail/'])
def test_serve_mount_resolution_and_shutdown(tmp_path, relative):
    (tmp_path / 'index.html').write_text('served')
    page = FakePage()
    browser = FakeBrowser([page])
    def provider():
        original_goto = page.goto
        def goto(url, **kwargs):
            base = url.split('/app/')[0] + '/app/'
            with urlopen(base) as response:
                assert response.read() == b'served'
            return original_goto(url, **kwargs)
        page.goto = goto
        return make_factory(browser)
    assert run_cli([relative, '--serve', str(tmp_path), '--mount', '/app/',
                    '--out', str(tmp_path / 'shot.png')], browser_factory=provider) == 0
    url = page.kwargs_for('goto')['url']
    assert urlsplit(url).path == '/app/' + ('' if relative == '.' else relative)
    with pytest.raises(OSError):
        urlopen(url, timeout=0.2)
