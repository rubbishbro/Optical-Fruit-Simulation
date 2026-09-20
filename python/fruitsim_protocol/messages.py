from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
import uuid


PROTOCOL_VERSION = 1
_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


class ProtocolError(ValueError):
    """Raised when a protocol document is malformed or unsafe to handle."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 160 or not _ID_RE.fullmatch(value):
        raise ProtocolError(f"{field} must be a short identifier")
    return value


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError(f"{field} must be an object")
    return value


def make_command(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    run_id: str | None = None,
    command_id: str | None = None,
) -> dict[str, Any]:
    document = {
        "protocol": PROTOCOL_VERSION,
        "type": "command",
        "command_id": command_id or f"cmd-{uuid.uuid4().hex}",
        "name": name,
        "run_id": run_id,
        "payload": payload or {},
        "client_ts": _now(),
    }
    validate_message(document)
    return document


def make_ack(command_id: str, accepted: bool, *, error: dict[str, Any] | None = None) -> dict[str, Any]:
    document = {
        "protocol": PROTOCOL_VERSION,
        "type": "command_ack",
        "command_id": command_id,
        "accepted": bool(accepted),
        "server_ts": _now(),
        "error": error,
    }
    validate_message(document)
    return document


def make_event(
    seq: int,
    *,
    run_id: str | None,
    kind: str,
    stage: str,
    status: str,
    payload: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    document = {
        "protocol": PROTOCOL_VERSION,
        "type": "event",
        "seq": seq,
        "event_id": event_id or f"evt-{uuid.uuid4().hex}",
        "run_id": run_id,
        "kind": kind,
        "stage": stage,
        "status": status,
        "server_ts": _now(),
        "payload": payload or {},
    }
    validate_message(document)
    return document


def make_hello(latest_seq: int) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL_VERSION,
        "type": "hello",
        "latest_seq": latest_seq,
        "server_ts": _now(),
    }


def validate_message(document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ProtocolError("message must be an object")
    if document.get("protocol") != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version: {document.get('protocol')!r}")
    message_type = document.get("type")
    if message_type == "command":
        _id(document.get("command_id"), "command_id")
        _id(document.get("name"), "name")
        _object(document.get("payload"), "payload")
        if document.get("run_id") is not None:
            _id(document.get("run_id"), "run_id")
        if not isinstance(document.get("client_ts"), str) or not document["client_ts"]:
            raise ProtocolError("client_ts must be a non-empty string")
    elif message_type == "command_ack":
        _id(document.get("command_id"), "command_id")
        if not isinstance(document.get("accepted"), bool):
            raise ProtocolError("accepted must be boolean")
        if document.get("error") is not None:
            _object(document["error"], "error")
        if not isinstance(document.get("server_ts"), str) or not document["server_ts"]:
            raise ProtocolError("server_ts must be a non-empty string")
    elif message_type == "event":
        if not isinstance(document.get("seq"), int) or document["seq"] < 1:
            raise ProtocolError("event.seq must be a positive integer")
        _id(document.get("event_id"), "event_id")
        for field in ("kind", "stage", "status"):
            _id(document.get(field), field)
        if document.get("run_id") is not None:
            _id(document.get("run_id"), "run_id")
        _object(document.get("payload"), "payload")
        if not isinstance(document.get("server_ts"), str) or not document["server_ts"]:
            raise ProtocolError("server_ts must be a non-empty string")
    elif message_type == "hello":
        if not isinstance(document.get("latest_seq"), int) or document["latest_seq"] < 0:
            raise ProtocolError("hello.latest_seq must be a non-negative integer")
    else:
        raise ProtocolError(f"unsupported message type: {message_type!r}")
    return document
