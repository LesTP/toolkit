"""Static serving edge cases beyond the phase acceptance suite."""
from __future__ import annotations

import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from toolkit.screenshot import static_server


def test_mount_without_trailing_slash_and_nested_query(tmp_path):
    nested = tmp_path / "detail"
    nested.mkdir()
    (nested / "index.html").write_text("nested content")
    with static_server(str(tmp_path), mount="/app") as base:
        assert base.endswith("/app/")
        with urlopen(base + "detail/?version=1", timeout=2) as response:
            assert response.read() == b"nested content"


@pytest.mark.parametrize("path", ["/application/index.html", "/app/../index.html",
                                  "/app/%2e%2e/index.html"])
def test_mount_boundary_and_traversal_return_404(tmp_path, path):
    (tmp_path / "index.html").write_text("private")
    with static_server(tmp_path, mount="/app/") as base:
        origin = base.removesuffix("/app/")
        with pytest.raises(HTTPError) as error:
            urlopen(origin + path, timeout=2)
        assert error.value.code == 404


def test_root_cannot_be_a_file(tmp_path):
    root = tmp_path / "file.html"
    root.write_text("content")
    with pytest.raises(FileNotFoundError):
        with static_server(root):
            pytest.fail("file root must be rejected")


@pytest.mark.parametrize("exceptional", [False, True])
def test_serving_thread_is_joined(tmp_path, exceptional):
    before = set(threading.enumerate())
    try:
        with static_server(tmp_path):
            workers = set(threading.enumerate()) - before
            assert len(workers) == 1
            if exceptional:
                raise RuntimeError("consumer failed")
    except RuntimeError:
        assert exceptional
    assert all(not worker.is_alive() for worker in workers)
