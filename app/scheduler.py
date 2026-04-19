from __future__ import annotations

import asyncio
import logging

from app.orchestrator import orchestrator
from app.state import app_state

logger = logging.getLogger(__name__)


class IssueScheduler:
    def __init__(self, interval_seconds: int = 300) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None

    async def _run_loop(self) -> None:
        while app_state.is_running:
            try:
                orchestrator.run_once()
            except Exception as exc:  # pragma: no cover
                logger.exception("Scheduler run failed: %s", exc)
            await asyncio.sleep(self.interval_seconds)

    async def start(self) -> None:
        if app_state.is_running:
            return
        app_state.is_running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        app_state.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


scheduler = IssueScheduler()
