"""Temporary HTTP serving for already-built static pages."""
from __future__ import annotations

from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Iterator
from urllib.parse import unquote, urlsplit
import posixpath


@contextmanager
def static_server(
    root: str | Path, *, mount: str = "/", host: str = "127.0.0.1",
    port: int = 0,
) -> Iterator[str]:
    """Serve root under a URL prefix, releasing the server on context exit."""
    directory = Path(root).resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Not an existing directory: {root}")
    if not mount.startswith("/"):
        raise ValueError("mount must start with '/'")
    prefix = mount.rstrip("/") + "/"

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def send_head(self):
            path = urlsplit(self.path).path
            normalized = posixpath.normpath(unquote(path))
            # Check both the literal path and traversal-normalized path so
            # requests cannot escape the mount via encoded '..' segments.
            if not path.startswith(prefix) or not (
                normalized == prefix.rstrip("/")
                or normalized.startswith(prefix)
            ):
                self.send_error(404)
                return None
            return super().send_head()

        def translate_path(self, path):
            return super().translate_path("/" + path[len(prefix):])

        def log_message(self, format, *args):
            # Library and CLI callers own their diagnostic output.
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05},
                    daemon=True)
    try:
        thread.start()
        yield f"http://{host}:{server.server_port}{prefix}"
    finally:
        if thread.ident is not None:
            server.shutdown()
            thread.join()
        server.server_close()
