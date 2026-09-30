from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http(url: str):
    try:
        response = urlopen(url, timeout=10)
    except HTTPError as error:
        return error.code, error.read()
    return response.status, response.read()


def _wait_http(url: str, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.2)
    raise AssertionError(f"service never became healthy: {url}")


# --- minimal masked WebSocket client (no third-party dependency) -------------
def _ws_connect(host: str, port: int):
    sock = socket.create_connection((host, port), timeout=15)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    ).encode()
    sock.sendall(request)
    buffer = b""
    while b"\r\n\r\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            raise AssertionError("websocket handshake closed")
        buffer += chunk
    assert buffer.split(b"\r\n", 1)[0].endswith(b"101 Switching Protocols")
    return sock


def _ws_send(sock, document: dict) -> None:
    payload = json.dumps(document, separators=(",", ":")).encode()
    mask = os.urandom(4)
    header = bytearray([0x81])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", length)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", length)
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    sock.sendall(bytes(header) + mask + masked)


def _recv_exact(sock, count: int) -> bytes:
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise AssertionError("websocket closed")
        data += chunk
    return data


def _ws_recv(sock) -> dict:
    while True:
        first = _recv_exact(sock, 2)
        opcode = first[0] & 0x0F
        masked = bool(first[1] & 0x80)
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", _recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack(">Q", _recv_exact(sock, 8))[0]
        mask = _recv_exact(sock, 4) if masked else b""
        data = _recv_exact(sock, length)
        if masked:
            data = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
        if opcode == 0x9:  # ping
            continue
        if opcode == 0x8:
            raise AssertionError("server closed the websocket")
        return json.loads(data.decode("utf-8"))


def _ws_wait_hello(sock) -> dict:
    # A broadcast from an in-flight Run can arrive before hello, so skip events.
    for _ in range(50):
        message = _ws_recv(sock)
        if message.get("type") == "hello":
            return message
    raise AssertionError("websocket hello was never received")


def _connect_ready(host: str, port: int, attempts: int = 8):
    """Connect and wait for hello, tolerating a slow first accept."""
    last_error: Exception | None = None
    for _ in range(attempts):
        sock = None
        try:
            sock = _ws_connect(host, port)
            sock.settimeout(3)
            _ws_wait_hello(sock)
            sock.settimeout(30)
            return sock
        except (OSError, AssertionError) as error:
            last_error = error
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            time.sleep(0.3)
    raise AssertionError(f"could not complete gateway hello: {last_error!r}")


@unittest.skipUnless(shutil.which("bash"), "bash is required")
class RunWebDemoScriptE2ETest(unittest.TestCase):
    def test_script_runs_gateway_static_and_reads_same_run(self) -> None:
        gateway_port = _free_port()
        web_port = _free_port()
        run_id = f"wp3_script_e2e_{os.getpid()}"
        with tempfile.TemporaryDirectory(prefix="fruitsim-script-e2e-") as directory:
            root = Path(directory)
            output_root = root / "runs"
            journal = root / "events.jsonl"
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHON_BIN": sys.executable,
                    "FRUITSIM_WEB_ROOT": str(TEMPLATE),
                    "FRUITSIM_DEMO_OUTPUT_ROOT": str(output_root),
                    "FRUITSIM_GATEWAY_JOURNAL": str(journal),
                    "FRUITSIM_WEB_PORT": str(web_port),
                    "FRUITSIM_GATEWAY_PORT": str(gateway_port),
                    "FRUITSIM_DEMO_BIND": "127.0.0.1",
                }
            )
            process = subprocess.Popen(
                ["bash", str(ROOT / "scripts" / "run_web_demo.sh")],
                cwd=str(ROOT),
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            sock = None
            try:
                _wait_http(f"http://127.0.0.1:{web_port}/health", 30)
                _wait_http(f"http://127.0.0.1:{web_port}/index.html", 30)

                # The static server exposes the same output root through the runs API.
                status, body = _http(f"http://127.0.0.1:{web_port}/api/runs/{run_id}")
                self.assertEqual(status, 404)

                sock = _connect_ready("127.0.0.1", gateway_port)

                _ws_send(
                    sock,
                    {
                        "protocol": 1,
                        "type": "command",
                        "command_id": f"e2e-{run_id}",
                        "name": "run.start",
                        "run_id": run_id,
                        "payload": {"mode": "math", "seed": 20260920, "samples": 6},
                        "client_ts": "2026-09-30T00:00:00Z",
                    },
                )
                completed = None
                deadline = time.time() + 180
                while time.time() < deadline:
                    message = _ws_recv(sock)
                    if message.get("type") == "event" and message.get("kind") == "run_completed":
                        completed = message
                        break
                    if message.get("type") == "command_ack" and not message.get("accepted"):
                        self.fail(f"run.start was rejected: {message.get('error')}")
                self.assertIsNotNone(completed, "run never completed")
                self.assertEqual(completed["payload"]["run_id"], run_id)

                status, body = _http(f"http://127.0.0.1:{web_port}/api/runs/{run_id}")
                self.assertEqual(status, 200)
                summary = json.loads(body)
                self.assertEqual(summary["run_id"], run_id)
                self.assertTrue(summary["complete"])
                artifact_ids = {item["artifact_id"] for item in summary["artifacts"]}
                self.assertIn("samples", artifact_ids)
                self.assertIn("spectra", artifact_ids)
                text = body.decode("utf-8")
                self.assertNotIn(str(output_root), text)
                self.assertNotIn("output_dir", text)

                status, content = _http(
                    f"http://127.0.0.1:{web_port}/api/runs/{run_id}/artifacts/samples"
                )
                self.assertEqual(status, 200)
                self.assertIn(b"sample_id", content)

                # Cross-run and traversal reads are refused by the server itself.
                self.assertEqual(_http(f"http://127.0.0.1:{web_port}/api/runs/other_run/artifacts/samples")[0], 404)
                self.assertEqual(_http(f"http://127.0.0.1:{web_port}/api/runs/..%2f{run_id}")[0], 404)

                # Reconnect-before-accept: resending the same command_id must be
                # idempotent and the journal must still carry the accepted event.
                resend_id = f"wp3_resend_{os.getpid()}"
                command = {
                    "protocol": 1,
                    "type": "command",
                    "command_id": f"e2e-resend-{resend_id}",
                    "name": "run.start",
                    "run_id": resend_id,
                    "payload": {"mode": "math", "seed": 20260920, "samples": 6},
                    "client_ts": "2026-09-30T00:00:00Z",
                }
                _ws_send(sock, command)
                sock.close()
                sock = _connect_ready("127.0.0.1", gateway_port)
                _ws_send(sock, command)  # same command_id
                _ws_send(sock, {"type": "replay", "after_seq": 0, "run_id": resend_id})
                acknowledged = False
                resend_completed = None
                deadline = time.time() + 180
                while time.time() < deadline:
                    message = _ws_recv(sock)
                    if message.get("type") == "command_ack":
                        self.assertTrue(message.get("accepted"), message.get("error"))
                        acknowledged = True
                    if (
                        message.get("type") == "event"
                        and message.get("kind") == "run_completed"
                        and message.get("payload", {}).get("run_id") == resend_id
                    ):
                        resend_completed = message
                        break
                self.assertTrue(acknowledged, "idempotent resend was not acknowledged")
                self.assertIsNotNone(resend_completed, "resend after reconnect never completed")
                self.assertTrue((output_root / resend_id).is_dir(), "the resent run did not produce one directory")
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                if process.poll() is None:
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    except (ProcessLookupError, PermissionError):
                        process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
