from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from typing import Any, Callable

from fruitsim_protocol.journal import EventJournal
from fruitsim_protocol.messages import (
    ProtocolError,
    make_ack,
    make_hello,
    validate_message,
)


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
CommandHandler = Callable[[dict[str, Any]], dict[str, Any] | None]


class WebSocketProtocolError(ValueError):
    pass


def _frame(payload: bytes, opcode: int = 0x1) -> bytes:
    first = 0x80 | (opcode & 0x0F)
    length = len(payload)
    if length < 126:
        return bytes([first, length]) + payload
    if length < 65536:
        return bytes([first, 126]) + length.to_bytes(2, "big") + payload
    return bytes([first, 127]) + length.to_bytes(8, "big") + payload


async def _read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    header = await reader.readexactly(2)
    first, second = header
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = int.from_bytes(await reader.readexactly(2), "big")
    elif length == 127:
        length = int.from_bytes(await reader.readexactly(8), "big")
    if length > 16 * 1024 * 1024:
        raise WebSocketProtocolError("WebSocket frame exceeds 16 MiB limit")
    if not masked:
        raise WebSocketProtocolError("client frames must be masked")
    mask = await reader.readexactly(4)
    data = bytearray(await reader.readexactly(length))
    for index in range(length):
        data[index] ^= mask[index % 4]
    return opcode, bytes(data)


async def _handshake(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    request = await reader.readuntil(b"\r\n\r\n")
    headers: dict[str, str] = {}
    for line in request.decode("latin1").split("\r\n")[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    if headers.get("upgrade", "").lower() != "websocket":
        raise WebSocketProtocolError("missing WebSocket upgrade header")
    key = headers.get("sec-websocket-key")
    if not key:
        raise WebSocketProtocolError("missing Sec-WebSocket-Key")
    accept = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
    )
    writer.write(response.encode("ascii"))
    await writer.drain()


class ProtocolHub:
    """Command router with idempotent acknowledgements and replayable events."""

    def __init__(self, journal: EventJournal) -> None:
        self.journal = journal
        self.handlers: dict[str, CommandHandler] = {}

    def register(self, name: str, handler: CommandHandler) -> None:
        self.handlers[name] = handler

    def handle(self, command: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        validate_message(command)
        command_id = command["command_id"]
        previous = self.journal.find_ack(command_id)
        if previous is not None:
            return previous, []
        handler = self.handlers.get(command["name"])
        if handler is None:
            ack = make_ack(command_id, False, error={"code": "unknown_command", "message": command["name"]})
            self.journal.record_ack(ack)
            return ack, []
        try:
            result = handler(command) or {}
            ack = make_ack(command_id, True)
            self.journal.record_ack(ack)
            event = self.journal.append_event(
                run_id=command.get("run_id"),
                kind=str(result.get("kind", "command_accepted")),
                stage=str(result.get("stage", "control")),
                status=str(result.get("status", "accepted")),
                payload={"command_id": command_id, **dict(result.get("payload", {}))},
            )
            return ack, [event]
        except Exception as exc:
            ack = make_ack(command_id, False, error={"code": "handler_error", "message": str(exc)[:500]})
            self.journal.record_ack(ack)
            return ack, []


class _Client:
    def __init__(self, writer: asyncio.StreamWriter) -> None:
        self.writer = writer
        self.lock = asyncio.Lock()

    async def send(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        async with self.lock:
            self.writer.write(_frame(payload))
            await self.writer.drain()


class ProtocolServer:
    def __init__(self, hub: ProtocolHub, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.hub = hub
        self.host = host
        self.port = port
        self.clients: set[_Client] = set()
        self.server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)

    async def close(self) -> None:
        for client in list(self.clients):
            client.writer.close()
        self.clients.clear()
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()

    async def serve_forever(self) -> None:
        await self.start()
        assert self.server is not None
        async with self.server:
            await self.server.serve_forever()

    async def broadcast(self, message: dict[str, Any]) -> None:
        stale: list[_Client] = []
        for client in list(self.clients):
            try:
                await client.send(message)
            except (ConnectionError, asyncio.IncompleteReadError):
                stale.append(client)
        for client in stale:
            self.clients.discard(client)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client: _Client | None = None
        try:
            await _handshake(reader, writer)
            client = _Client(writer)
            self.clients.add(client)
            await client.send(make_hello(self.hub.journal.latest_seq))
            while True:
                opcode, payload = await _read_frame(reader)
                if opcode == 0x8:
                    break
                if opcode == 0x9:
                    writer.write(_frame(payload, opcode=0xA))
                    await writer.drain()
                    continue
                if opcode != 0x1:
                    raise WebSocketProtocolError("only text frames are supported")
                message = json.loads(payload.decode("utf-8"))
                if message.get("type") == "replay":
                    after_seq = int(message.get("after_seq", 0))
                    run_id = message.get("run_id")
                    for event in self.hub.journal.replay(after_seq=after_seq, run_id=run_id):
                        await client.send(event)
                    continue
                ack, events = self.hub.handle(message)
                await client.send(ack)
                for event in events:
                    await self.broadcast(event)
        except (asyncio.IncompleteReadError, ConnectionError, WebSocketProtocolError, json.JSONDecodeError, ProtocolError):
            pass
        finally:
            if client is not None:
                self.clients.discard(client)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
