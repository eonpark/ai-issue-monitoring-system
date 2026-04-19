from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class InMemoryDB:
    """Simple placeholder DB implementation."""

    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []

    def save_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        stored = {
            "id": len(self._items) + 1,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            **issue,
        }
        self._items.append(stored)
        return stored

    def list_issues(self) -> list[dict[str, Any]]:
        return list(self._items)


db = InMemoryDB()
