#!/usr/bin/env python3
"""Real A/B integration: live Gateway + HTTP runs API + real headless Chrome.

Unlike scripts/tests/test_demo_browser.py (DOM + stubbed events), this launches
an actual ``fruitsim_gateway`` and ``serve_webgl_demo.py --runs-root`` pair, then
drives the real page in Chrome via the DevTools protocol to create two small
math Runs and read each Run's results through ``/api/runs``. The Gateway port is
injected per-run through the URL; no global configuration is touched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_ok(url: str) -> bool:
    try:
        with urlopen(url, timeout=2) as response:
            return response.status == 200
    except (URLError, OSError):
        return False


def wait_http(url: str, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _http_ok(url):
            return
        time.sleep(0.2)
    raise SystemExit(f"service did not become healthy: {url}")


class CDP:
    def __init__(self, ws_url: str) -> None:
        import websocket  # websocket-client

        self.ws = websocket.create_connection(ws_url, timeout=30)
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        message_id = self._id
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == message_id:
                return message

    def evaluate(self, expression: str) -> object:
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": False},
        )
        return result.get("result", {}).get("result", {}).get("value")


def main() -> int:
    try:
        import websocket  # noqa: F401
    except ImportError:
        print("websocket-client is required for the demo E2E runner", file=sys.stderr)
        return 3

    gateway_port = free_port()
    web_port = free_port()
    debug_port = free_port()
    suffix = str(int(time.time() * 1000))
    with tempfile.TemporaryDirectory(prefix="fruitsim-e2e-") as directory:
        root = Path(directory)
        output_root = root / "runs"
        journal = root / "events.jsonl"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "python")
        environment["FRUITSIM_DEMO_OUTPUT_ROOT"] = str(output_root)
        gateway = subprocess.Popen(
            [sys.executable, "-m", "fruitsim_gateway", "--bind", "127.0.0.1", "--port", str(gateway_port),
             "--journal", str(journal), "--output-root", str(output_root), "--repo-root", str(ROOT)],
            cwd=str(ROOT), env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        static = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "serve_webgl_demo.py"), "--root", str(TEMPLATE),
             "--bind", "127.0.0.1", "--port", str(web_port), "--runs-root", str(output_root)],
            cwd=str(ROOT), env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        profile = tempfile.mkdtemp(prefix="fruitsim-chrome-")
        chrome = None
        try:
            wait_http(f"http://127.0.0.1:{web_port}/health", 20)
            wait_http(f"http://127.0.0.1:{web_port}/index.html", 20)
            chrome = subprocess.Popen(
                ["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
                 "--disable-dev-shm-usage", "--disable-extensions",
                 "--remote-allow-origins=*",
                 f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile}", "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
            )
            wait_http(f"http://127.0.0.1:{debug_port}/json/version", 25)
            page_url = (
                f"http://127.0.0.1:{web_port}/index.html?demoe2e=1"
                f"&gateway_port={gateway_port}&e2e_suffix={suffix}"
            )
            new_target = Request(
                f"http://127.0.0.1:{debug_port}/json/new?{quote(page_url, safe='')}", method="PUT"
            )
            target = json.loads(urlopen(new_target, timeout=10).read())
            cdp = CDP(target["webSocketDebuggerUrl"])
            cdp.call("Runtime.enable")
            deadline = time.time() + 300
            done = False
            while time.time() < deadline:
                if cdp.evaluate("window.__demoE2EReportDone === true") is True:
                    done = True
                    break
                time.sleep(0.5)
            report = cdp.evaluate("JSON.stringify(window.__demoE2EReport)")
            payload = json.loads(report) if isinstance(report, str) else {"pass": False, "error": "no report"}
            if not done:
                payload.setdefault("error", "harness did not finish in time")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            ok = bool(done and payload.get("pass"))
            if not ok:
                print("demo E2E failed", file=sys.stderr)
                return 1
            return 0
        finally:
            for process in (chrome, static, gateway):
                if process is not None:
                    import signal

                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    except (ProcessLookupError, PermissionError):
                        process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                        except (ProcessLookupError, PermissionError):
                            process.kill()
            import shutil

            shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
