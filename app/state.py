from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass
class AppState:
    """Shared in-memory application state."""

    is_running: bool = False
    last_result: dict[str, Any] | None = None
    last_run_time: str | None = None
    run_count: int = 0
    lock: Lock = field(default_factory=Lock)

    def update_result(self, result: dict[str, Any]) -> None:
        with self.lock:
            self.last_result = result
            self.run_count += 1

    def get_last_run_time(self) -> str | None:
        with self.lock:
            return self.last_run_time

    def set_last_run_time(self, timestamp: str) -> None:
        with self.lock:
            self.last_run_time = timestamp

    def touch_last_run_time(self) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        self.set_last_run_time(timestamp)
        return timestamp


app_state = AppState()
