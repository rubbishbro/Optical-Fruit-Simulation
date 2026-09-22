#!/usr/bin/env python3
"""Run the real Fruitsim ML DOM interaction harness in headless Chrome."""

from __future__ import annotations

import html
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    web_root = Path(os.environ.get("FRUITSIM_BROWSER_ROOT", str(TEMPLATE))).resolve()
    port = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(web_root)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.25)
        result = subprocess.run(
            [
                "google-chrome",
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--virtual-time-budget=12000",
                "--dump-dom",
                f"http://127.0.0.1:{port}/index.html?harness=1",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    finally:
        server.terminate()
        server.wait(timeout=5)

    output = result.stdout
    marker = '<pre id="ml-p1-harness-result"'
    start = output.find(marker)
    if start < 0:
        print("browser harness marker missing", file=sys.stderr)
        print(result.stderr[-4000:], file=sys.stderr)
        return 1
    start = output.find(">", start) + 1
    end = output.find("</pre>", start)
    payload = html.unescape(output[start:end])
    try:
        report = json.loads(payload)
    except json.JSONDecodeError:
        print(repr(payload), file=sys.stderr)
        print(output[-4000:], file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if result.returncode != 0 or not report.get("pass"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
