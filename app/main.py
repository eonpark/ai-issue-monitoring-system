from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app.db import db
from app.orchestrator import orchestrator
from app.scheduler import scheduler
from app.state import app_state

load_dotenv()


@asynccontextmanager
async def lifespan(_: FastAPI):
    auto_start = os.getenv("AUTO_START_SCHEDULER", "false").lower() == "true"
    if auto_start:
        await scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(
    title="Real-time Issue Monitoring System",
    description="실시간 이슈 수집 및 분석 시스템 기본 템플릿",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
def read_root() -> dict:
    return {
        "service": app.title,
        "status": "running",
        "scheduler_running": app_state.is_running,
    }


@app.post("/run")
def run_pipeline(query: str = "한국 실시간 주요 이슈") -> dict:
    return orchestrator.run_once(query=query)


@app.get("/issues")
def get_issues() -> dict:
    return {"count": len(db.list_issues()), "items": db.list_issues()}


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "run_count": app_state.run_count,
        "last_result": app_state.last_result,
    }
