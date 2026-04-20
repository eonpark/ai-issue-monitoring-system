from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


class PipelineScheduler:
    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler()
        self._started = False

    def start(self, job_func) -> None:
        if self._started:
            return
        self._scheduler.add_job(
            job_func,
            trigger="interval",
            minutes=5,
            id="pipeline_job",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()
        self._started = True
        logger.info("Scheduler started")

    def shutdown(self) -> None:
        if not self._started:
            return
        self._scheduler.shutdown(wait=False)
        self._started = False
        logger.info("Scheduler stopped")

    def get_status(self, *, is_running: bool = False, last_run_time: str | None = None) -> dict[str, Any]:
        job = self._scheduler.get_job("pipeline_job") if self._started else None
        next_run_time = None
        if job is not None and job.next_run_time is not None:
            next_run_time = job.next_run_time.isoformat()

        return {
            "started": self._started,
            "running": is_running,
            "interval_minutes": 5,
            "next_run_time": next_run_time,
            "last_run_time": last_run_time,
        }


pipeline_scheduler = PipelineScheduler()
