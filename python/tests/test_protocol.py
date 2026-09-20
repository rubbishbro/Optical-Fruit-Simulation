from __future__ import annotations

import asyncio
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

from fruitsim_gateway.server import ProtocolHub, ProtocolServer, _frame
from fruitsim_protocol import EventJournal, LatestValueBuffer, make_command, validate_message


def _masked_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    mask = b"fsim"
    encoded = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    length = len(encoded)
    if length < 126:
        header = bytes([0x80 | opcode, 0x80 | length])
    else:
        header = bytes([0x80 | opcode, 0x80 | 126]) + length.to_bytes(2, "big")
    return header + mask + encoded


async def _read_server_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    header = await reader.readexactly(2)
    first, second = header
    length = second & 0x7F
    if length == 126:
        length = int.from_bytes(await reader.readexactly(2), "big")
    elif length == 127:
        length = int.from_bytes(await reader.readexactly(8), "big")
    return first & 0x0F, await reader.readexactly(length)


class ProtocolTests(unittest.TestCase):
    def test_journal_replay_and_command_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = EventJournal(Path(directory) / "events.jsonl")
            hub = ProtocolHub(journal)
            hub.register("run.start", lambda command: {"stage": "queued", "status": "queued"})
            command = make_command("run.start", run_id="run-a", command_id="cmd-a")
            first_ack, first_events = hub.handle(command)
            second_ack, second_events = hub.handle(command)
            self.assertEqual(first_ack, second_ack)
            self.assertEqual(len(first_events), 1)
            self.assertEqual(second_events, [])
            self.assertEqual(journal.latest_seq, 1)
            self.assertEqual(len(journal.replay(after_seq=0, run_id="run-a")), 1)
            self.assertEqual(len(journal.replay(after_seq=1)), 0)

    def test_latest_value_buffer_drops_stale_interaction_state(self) -> None:
        buffer = LatestValueBuffer()
        buffer.put("wavelength_nm", 600)
        buffer.put("wavelength_nm", 700)
        self.assertEqual(buffer.pop_snapshot(), {"wavelength_nm": 700})
        self.assertEqual(buffer.pop_snapshot(), {})

    def test_message_validation_rejects_wrong_protocol(self) -> None:
        with self.assertRaises(ValueError):
            validate_message({"protocol": 99, "type": "hello", "latest_seq": 0})

    def test_websocket_handshake_ack_event_and_replay(self) -> None:
        asyncio.run(self._websocket_flow())

    async def _websocket_flow(self) -> None:
        journal = EventJournal()
        hub = ProtocolHub(journal)
        hub.register("run.start", lambda command: {"stage": "queued", "status": "queued"})
        server = ProtocolServer(hub, "127.0.0.1", 0)
        await server.start()
        assert server.server is not None
        port = server.server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
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
        opcode, payload = await _read_server_frame(reader)
        self.assertEqual(opcode, 1)
        self.assertEqual(json.loads(payload)["type"], "hello")
        command = make_command("run.start", run_id="run-a", command_id="cmd-a")
        writer.write(_masked_frame(json.dumps(command).encode("utf-8")))
        await writer.drain()
        _, ack_payload = await _read_server_frame(reader)
        _, event_payload = await _read_server_frame(reader)
        self.assertTrue(json.loads(ack_payload)["accepted"])
        self.assertEqual(json.loads(event_payload)["seq"], 1)
        replay = {"type": "replay", "after_seq": 0}
        writer.write(_masked_frame(json.dumps(replay).encode("utf-8")))
        await writer.drain()
        _, replay_payload = await _read_server_frame(reader)
        self.assertEqual(json.loads(replay_payload)["event_id"], json.loads(event_payload)["event_id"])
        writer.close()
        await writer.wait_closed()
        await server.close()


if __name__ == "__main__":
    unittest.main()
