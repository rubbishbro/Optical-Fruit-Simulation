from __future__ import annotations

from threading import Lock
from typing import Any


class LatestValueBuffer:
    """Thread-safe latest-value-wins buffer for high-frequency UI state."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._values: dict[str, Any] = {}

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._values[key] = value

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._values)

    def pop_snapshot(self) -> dict[str, Any]:
        with self._lock:
            values = dict(self._values)
            self._values.clear()
            return values
