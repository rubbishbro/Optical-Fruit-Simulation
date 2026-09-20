#!/usr/bin/env python3
"""Serve a Unity WebGL build with browser-safe headers and compressed assets."""

from __future__ import annotations

import argparse
import json
from io import BytesIO
import mimetypes
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class WebGLRequestHandler(SimpleHTTPRequestHandler):
    server_version = "FruitsimWebGL/1"

    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/health":
            body = json.dumps({"ok": True, "service": "fruitsim-webgl-static"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def send_head(self):  # noqa: N802 - stdlib handler API
        requested = Path(self.translate_path(self.path))
        served = requested
        encoding = None
        content_path = requested
        if served.is_file() and served.suffix in {".br", ".gz"}:
            encoding = "br" if served.suffix == ".br" else "gzip"
            content_path = Path(str(served)[: -len(served.suffix)])
        if not served.is_file():
            for suffix, value in ((".br", "br"), (".gz", "gzip")):
                candidate = Path(str(requested) + suffix)
                if candidate.is_file():
                    served = candidate
                    encoding = value
                    content_path = requested
                    break
        if not served.is_file():
            return super().send_head()
        try:
            content = served.read_bytes()
        except OSError:
            self.send_error(404, "File not readable")
            return None
        content_type = mimetypes.guess_type(str(content_path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        if encoding:
            self.send_header("Content-Encoding", encoding)
        self.end_headers()
        return BytesIO(content)


def main() -> int:
    parser = argparse.ArgumentParser(prog="serve_webgl_demo")
    parser.add_argument("--root", type=Path, default=Path("apps/fruitsim_unity/build/WebGL"))
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"WebGL build directory does not exist: {root}")
    server = ThreadingHTTPServer((args.bind, args.port), lambda *items: WebGLRequestHandler(*items, directory=str(root)))
    print(f"Serving {root} at http://{args.bind}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
