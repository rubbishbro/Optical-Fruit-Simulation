from __future__ import annotations

from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "serve_webgl_demo.py"
SPEC = importlib.util.spec_from_file_location("serve_webgl_demo", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WebGLServerTests(unittest.TestCase):
    def test_explicit_gzip_asset_has_uncompressed_mime_and_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Build").mkdir()
            (root / "Build" / "WebGL.framework.js.gz").write_bytes(b"gzip-data")
            handler = partial(MODULE.WebGLRequestHandler, directory=str(root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                connection = HTTPConnection("127.0.0.1", port, timeout=5)
                connection.request("GET", "/Build/WebGL.framework.js.gz")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Encoding"), "gzip")
                self.assertEqual(response.getheader("Content-Type"), "text/javascript")
                self.assertEqual(response.read(), b"gzip-data")
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
