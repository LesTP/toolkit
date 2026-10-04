"""Acceptance tests: static_server context manager."""

from __future__ import annotations

import socket
import urllib.request
from pathlib import Path

import pytest


def _fetch(url: str) -> tuple[int, bytes]:
    """Return (status_code, body) for a GET request."""
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""


# ---------------------------------------------------------------------------
# Basic file serving
# ---------------------------------------------------------------------------

def test_serves_file_under_mount(tmp_path):
    from toolkit.screenshot import static_server
    (tmp_path / "index.html").write_text("<h1>hello</h1>")
    with static_server(tmp_path, mount="/test/") as base:
        status, body = _fetch(base + "index.html")
    assert status == 200
    assert b"hello" in body


def test_base_url_ends_with_slash(tmp_path):
    from toolkit.screenshot import static_server
    with static_server(tmp_path, mount="/app/") as base:
        assert base.endswith("/")


def test_base_url_includes_mount(tmp_path):
    from toolkit.screenshot import static_server
    with static_server(tmp_path, mount="/my-app/") as base:
        assert "/my-app/" in base


def test_base_url_default_mount_is_root(tmp_path):
    from toolkit.screenshot import static_server
    (tmp_path / "hello.txt").write_text("ok")
    with static_server(tmp_path) as base:
        status, body = _fetch(base + "hello.txt")
    assert status == 200


# ---------------------------------------------------------------------------
# 404 outside mount
# ---------------------------------------------------------------------------

def test_404_outside_mount(tmp_path):
    from toolkit.screenshot import static_server
    (tmp_path / "page.html").write_text("<p>secret</p>")
    with static_server(tmp_path, mount="/app/") as base:
        # Strip the mount and request at root level.
        host_port = base.split("/app/")[0]
        status, _ = _fetch(host_port + "/page.html")
    assert status == 404


# ---------------------------------------------------------------------------
# Ephemeral port
# ---------------------------------------------------------------------------

def test_ephemeral_port_is_nonzero(tmp_path):
    from toolkit.screenshot import static_server
    with static_server(tmp_path, port=0) as base:
        # Extract port from URL like http://127.0.0.1:PORT/
        port_str = base.split(":")[2].split("/")[0]
        assert int(port_str) > 0


def test_loopback_only_by_default(tmp_path):
    from toolkit.screenshot import static_server
    with static_server(tmp_path) as base:
        assert base.startswith("http://127.0.0.1:")


# ---------------------------------------------------------------------------
# Server shuts down after with block
# ---------------------------------------------------------------------------

def test_server_shuts_down_after_context(tmp_path):
    from toolkit.screenshot import static_server
    with static_server(tmp_path) as base:
        port_str = base.split(":")[2].split("/")[0]
        port = int(port_str)

    # After the with block the port should be released.
    with pytest.raises(Exception):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)


def test_server_shuts_down_on_exception(tmp_path):
    from toolkit.screenshot import static_server
    port_captured = None
    try:
        with static_server(tmp_path) as base:
            port_str = base.split(":")[2].split("/")[0]
            port_captured = int(port_str)
            raise RuntimeError("deliberate")
    except RuntimeError:
        pass

    assert port_captured is not None
    with pytest.raises(Exception):
        urllib.request.urlopen(f"http://127.0.0.1:{port_captured}/", timeout=1)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_file_not_found_error_for_missing_root(tmp_path):
    from toolkit.screenshot import static_server
    missing = tmp_path / "does_not_exist"
    with pytest.raises(FileNotFoundError):
        with static_server(missing):
            pass


def test_value_error_if_mount_no_leading_slash(tmp_path):
    from toolkit.screenshot import static_server
    with pytest.raises(ValueError):
        with static_server(tmp_path, mount="no-slash/"):
            pass
