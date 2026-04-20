from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.db import get_issues, get_last_run, save_issues, save_run_result
from app.orchestrator import orchestrator
from app.scheduler import pipeline_scheduler
from app.state import app_state

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Real-time Issue Monitoring API",
    description="기존 agent 시스템을 감싸는 FastAPI 서버",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LAST_RESULT: dict[str, Any] | None = None


def _restore_result_from_db() -> dict[str, Any] | None:
    try:
        last_run = get_last_run()
    except Exception as exc:  # pragma: no cover
        logger.exception("DB restore failed: %s", exc)
        return None

    if last_run is not None:
        issues = get_issues(run_id=last_run.get("id"))
        return {
            "final_step": last_run.get("final_step"),
            "actions": last_run.get("actions", []),
            "total": last_run.get("total", 0),
            "processed": last_run.get("processed", 0),
            "sent": last_run.get("sent", 0),
            "message": last_run.get("message"),
            "data": issues,
            "publish_result": last_run.get("publish_result"),
            "dedup": last_run.get("dedup", {"before": 0, "after": 0, "duplicates": 0}),
            "metrics": last_run.get("metrics", {}),
            "last_error": last_run.get("last_error"),
            "retry_count": None,
            "last_run_time": last_run.get("last_run_time") or last_run.get("created_at"),
        }

    issues = get_issues()
    if not issues:
        return None
    last_created_at = issues[0].get("created_at")
    return {
        "final_step": "restored",
        "actions": ["db_restore"],
        "total": len(issues),
        "processed": len(issues),
        "sent": 0,
        "message": None,
        "data": issues,
        "publish_result": None,
        "dedup": {"before": 0, "after": len(issues), "duplicates": 0},
        "metrics": {},
        "last_error": None,
        "retry_count": None,
        "last_run_time": last_created_at,
    }


def _execute_pipeline(trigger: str) -> dict[str, Any] | None:
    global LAST_RESULT

    prefix = "Scheduler" if trigger == "scheduler" else "API"
    with app_state.lock:
        if app_state.is_running:
            logger.info("%s: skipped (already running)", prefix)
            return None
        app_state.is_running = True

    try:
        logger.info("%s: pipeline started", prefix)
        LAST_RESULT = orchestrator.run_pipeline()
        try:
            run_id = save_run_result(LAST_RESULT)
            issues_to_save = LAST_RESULT.get("data") if isinstance(LAST_RESULT, dict) else []
            saved_count = save_issues(issues_to_save, run_id=run_id)
            logger.info("DB: saved=%s issues", saved_count)
        except Exception as exc:  # pragma: no cover
            logger.exception("DB save failed: %s", exc)
        logger.info("%s: pipeline finished", prefix)
        return LAST_RESULT
    except Exception as exc:  # pragma: no cover
        logger.exception("%s pipeline failed: %s", prefix, exc)
        return LAST_RESULT
    finally:
        with app_state.lock:
            app_state.is_running = False


@app.get("/")
def read_root() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/app.js")
def read_app_js() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "app.js", media_type="application/javascript")


@app.get("/style.css")
def read_style_css() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "style.css", media_type="text/css")


@app.post("/run")
def run_pipeline() -> dict[str, Any]:
    global LAST_RESULT
    result = _execute_pipeline("api")
    if result is not None:
        LAST_RESULT = result
    if LAST_RESULT is None:
        LAST_RESULT = _restore_result_from_db()
    logger.info(
        "API /run completed: final_step=%s total=%s processed=%s sent=%s",
        LAST_RESULT.get("final_step"),
        LAST_RESULT.get("total"),
        LAST_RESULT.get("processed"),
        LAST_RESULT.get("sent"),
    )
    return LAST_RESULT


@app.get("/result")
def get_last_result() -> dict[str, Any]:
    global LAST_RESULT
    if LAST_RESULT is None:
        LAST_RESULT = _restore_result_from_db()
    if isinstance(LAST_RESULT, dict):
        data = LAST_RESULT.get("data") or []
        result_size = len(data) if isinstance(data, list) else 0
    else:
        result_size = 0
    logger.info("API /result served: data_count=%s", result_size)
    return {"result": LAST_RESULT}


@app.get("/issues")
def read_issues() -> dict[str, Any]:
    try:
        issues = get_issues()
        logger.info("DB: loaded=%s issues", len(issues))
        return {"issues": issues}
    except Exception as exc:  # pragma: no cover
        logger.exception("DB read failed: %s", exc)
        return {"issues": []}


@app.get("/scheduler-status")
def read_scheduler_status() -> dict[str, Any]:
    return {
        "scheduler": pipeline_scheduler.get_status(
            is_running=app_state.is_running,
            last_run_time=app_state.get_last_run_time(),
        )
    }


@app.on_event("startup")
def start_scheduler() -> None:
    pipeline_scheduler.start(lambda: _execute_pipeline("scheduler"))


@app.on_event("shutdown")
def stop_scheduler() -> None:
    pipeline_scheduler.shutdown()
