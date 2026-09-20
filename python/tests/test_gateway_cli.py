from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fruitsim_protocol import make_command


def _masked_frame(payload: bytes) -> bytes:
    mask = b"fsim"
    encoded = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    length = len(encoded)
    if length < 126:
        header = bytes([0x81, 0x80 | length])
    else:
        header = bytes([0x81, 0x80 | 126]) + length.to_bytes(2, "big")
    return header + mask + encoded


async def _read_frame(reader: asyncio.StreamReader) -> dict:
    header = await reader.readexactly(2)
    length = header[1] & 0x7F
    if length == 126:
        length = int.from_bytes(await reader.readexactly(2), "big")
    elif length == 127:
        length = int.from_bytes(await reader.readexactly(8), "big")
    return json.loads((await reader.readexactly(length)).decode("utf-8"))


class GatewayCliE2ETest(unittest.TestCase):
    def test_cli_websocket_runs_real_math_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = root / "events.jsonl"
            output_root = root / "runs"
            port = 18766
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(Path.cwd() / "python")
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "fruitsim_gateway",
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--journal",
                    str(journal),
                    "--output-root",
                    str(output_root),
                    "--repo-root",
                    str(Path.cwd()),
                ],
                cwd=Path.cwd(),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                asyncio.run(self._exercise(process, port, output_root))
            finally:
                process.terminate()
                process.wait(timeout=10)
                if process.stdout is not None:
                    process.stdout.close()

    async def _exercise(self, process: subprocess.Popen[str], port: int, output_root: Path) -> None:
        reader = None
        writer = None
        for _ in range(100):
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                self.fail(f"gateway exited before listening: {output}")
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                break
            except OSError:
                await asyncio.sleep(0.05)
        self.assertIsNotNone(reader)
        self.assertIsNotNone(writer)
        assert reader is not None and writer is not None

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        writer.write((
            "GET /ws HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii"))
        await writer.drain()
        handshake = await reader.readuntil(b"\r\n\r\n")
        self.assertIn(b"101 Switching Protocols", handshake)
        hello = await _read_frame(reader)
        self.assertEqual(hello["type"], "hello")

        command = make_command("run.start", run_id="cli-e2e", payload={"mode": "math", "seed": 20260919, "samples": 20})
        writer.write(_masked_frame(json.dumps(command).encode("utf-8")))
        await writer.drain()
        ack = await _read_frame(reader)
        self.assertTrue(ack["accepted"])

        events: list[dict] = []
        while True:
            event = await asyncio.wait_for(_read_frame(reader), timeout=30)
            events.append(event)
            if event.get("kind") == "run_completed":
                break
            self.assertNotEqual(event.get("kind"), "run_failed", events)

        self.assertGreaterEqual(len(events), 3)
        manifest = output_root / "cli-e2e" / "manifest.json"
        status = output_root / "cli-e2e" / "status.json"
        self.assertTrue(manifest.is_file())
        self.assertTrue(status.is_file())
        self.assertEqual(json.loads(status.read_text(encoding="utf-8"))["state"], "completed")
        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    unittest.main()
