from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .messages import make_event, validate_message


class EventJournal:
    """Append-only event journal with replay and command idempotency."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._records: list[dict[str, Any]] = []
        self._latest_seq = 0
        self._acks: dict[str, dict[str, Any]] = {}
        if self.path and self.path.exists():
            self._load()

    @property
    def latest_seq(self) -> int:
        return self._latest_seq

    def _load(self) -> None:
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            self._records.append(record)
            if record.get("type") == "event":
                validate_message(record)
                self._latest_seq = max(self._latest_seq, record["seq"])
            elif record.get("record_type") == "command_ack":
                ack = record.get("ack")
                if isinstance(ack, dict):
                    validate_message(ack)
                    self._acks[ack["command_id"]] = ack

    def _append(self, record: dict[str, Any]) -> None:
        self._records.append(record)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                stream.flush()

    def append_event(
        self,
        *,
        run_id: str | None,
        kind: str,
        stage: str,
        status: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = make_event(
            self._latest_seq + 1,
            run_id=run_id,
            kind=kind,
            stage=stage,
            status=status,
            payload=payload,
        )
        self._latest_seq = event["seq"]
        self._append(event)
        return event

    def record_ack(self, ack: dict[str, Any]) -> None:
        validate_message(ack)
        self._acks[ack["command_id"]] = ack
        self._append({"record_type": "command_ack", "ack": ack})

    def find_ack(self, command_id: str) -> dict[str, Any] | None:
        return self._acks.get(command_id)

    def replay(self, *, after_seq: int = 0, run_id: str | None = None) -> list[dict[str, Any]]:
        return [
            record for record in self._records
            if record.get("type") == "event"
            and record["seq"] > after_seq
            and (run_id is None or record.get("run_id") == run_id)
        ]
