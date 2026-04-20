from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "issues.db"


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _initialize() -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                score INTEGER NOT NULL,
                status TEXT NOT NULL,
                issue_type TEXT NOT NULL DEFAULT '',
                impact_scope TEXT NOT NULL DEFAULT '',
                action_required INTEGER NOT NULL DEFAULT 0,
                change_nature TEXT NOT NULL DEFAULT '',
                major_issue INTEGER NOT NULL DEFAULT 0,
                validation_reason TEXT NOT NULL DEFAULT '',
                embedding TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                final_step TEXT NOT NULL DEFAULT '',
                actions TEXT NOT NULL DEFAULT '[]',
                total INTEGER NOT NULL DEFAULT 0,
                processed INTEGER NOT NULL DEFAULT 0,
                sent INTEGER NOT NULL DEFAULT 0,
                dedup_before INTEGER NOT NULL DEFAULT 0,
                dedup_after INTEGER NOT NULL DEFAULT 0,
                dedup_duplicates INTEGER NOT NULL DEFAULT 0,
                message TEXT,
                publish_status TEXT,
                publish_detail TEXT,
                last_error TEXT,
                metrics TEXT NOT NULL DEFAULT '{}',
                last_run_time TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        _ensure_column(conn, "issues", "run_id", "INTEGER")
        _ensure_column(conn, "issues", "issue_type", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "issues", "impact_scope", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "issues", "action_required", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "issues", "change_nature", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "issues", "major_issue", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "issues", "validation_reason", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "issues", "embedding", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "run_history", "dedup_before", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "run_history", "dedup_after", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "run_history", "dedup_duplicates", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "run_history", "metrics", "TEXT NOT NULL DEFAULT '{}'")
        conn.commit()


def save_run_result(result: dict[str, Any] | None) -> int | None:
    _initialize()
    if not isinstance(result, dict):
        return None

    created_at = datetime.now(timezone.utc).isoformat()
    publish_result = result.get("publish_result") if isinstance(result.get("publish_result"), dict) else {}
    dedup = result.get("dedup") if isinstance(result.get("dedup"), dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}

    with _get_connection() as conn:
        _ensure_column(conn, "run_history", "dedup_before", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "run_history", "dedup_after", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "run_history", "dedup_duplicates", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "run_history", "metrics", "TEXT NOT NULL DEFAULT '{}'")
        cursor = conn.execute(
            """
            INSERT INTO run_history (
                final_step, actions, total, processed, sent,
                dedup_before, dedup_after, dedup_duplicates,
                message,
                publish_status, publish_detail, last_error, metrics, last_run_time, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(result.get("final_step", "")).strip(),
                json_dumps(result.get("actions", [])),
                _safe_score(result.get("total")),
                _safe_score(result.get("processed")),
                _safe_score(result.get("sent")),
                _safe_score(dedup.get("before")),
                _safe_score(dedup.get("after")),
                _safe_score(dedup.get("duplicates")),
                result.get("message"),
                publish_result.get("status"),
                publish_result.get("detail"),
                result.get("last_error"),
                json_dumps(metrics),
                result.get("last_run_time"),
                created_at,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def save_issues(issues: list[dict[str, Any]] | None, run_id: int | None = None) -> int:
    _initialize()
    if not issues:
        return 0
    rows = []
    created_at = datetime.now(timezone.utc).isoformat()

    for issue in issues:
        title = str(issue.get("title", "")).strip()
        url = str(issue.get("url", "")).strip()
        if not title or not url:
            continue

        rows.append(
            (
                run_id,
                title,
                str(issue.get("summary", "")).strip(),
                _safe_score(issue.get("score")),
                str(issue.get("status", "")).strip() or "UNKNOWN",
                str(issue.get("issue_type", "")).strip(),
                str(issue.get("impact_scope", "")).strip(),
                str(issue.get("change_nature", "")).strip(),
                1 if bool(issue.get("major_issue", False)) else 0,
                str(issue.get("validation_reason", "")).strip(),
                _serialize_embedding(issue.get("embedding")),
                url,
                created_at,
            )
        )

    if not rows:
        return 0

    with _get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO issues (
                run_id, title, summary, score, status,
                issue_type, impact_scope, change_nature, major_issue, validation_reason, embedding,
                url, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    return len(rows)


def get_issues(run_id: int | None = None) -> list[dict[str, Any]]:
    _initialize()
    query = """
        SELECT
            id,
            run_id,
            title,
            summary,
            score,
            status,
            issue_type,
            impact_scope,
            change_nature,
            major_issue,
            validation_reason,
            embedding,
            url,
            created_at
        FROM issues
    """
    params: tuple[Any, ...] = ()
    if run_id is not None:
        query += " WHERE run_id = ?"
        params = (run_id,)
    query += " ORDER BY id DESC"
    with _get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_normalize_row(dict(row)) for row in rows]


def get_recent_issues(days: int = 3, limit: int = 200) -> list[dict[str, Any]]:
    _initialize()
    cutoff = _cutoff_iso(days)
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                run_id,
                title,
                summary,
                score,
                status,
                issue_type,
                impact_scope,
                change_nature,
                major_issue,
                validation_reason,
                embedding,
                url,
                created_at
            FROM issues
            WHERE created_at >= ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()
    return [_normalize_row(dict(row)) for row in rows]


def get_last_run() -> dict[str, Any] | None:
    _initialize()
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                id,
                final_step,
                actions,
                total,
                processed,
                sent,
                dedup_before,
                dedup_after,
                dedup_duplicates,
                message,
                publish_status,
                publish_detail,
                last_error,
                metrics,
                last_run_time,
                created_at
            FROM run_history
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return _normalize_run_row(dict(row))


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    row.pop("action_required", None)
    row["major_issue"] = bool(row.get("major_issue", 0))
    row["embedding"] = _deserialize_embedding(row.get("embedding"))
    return row


def _normalize_run_row(row: dict[str, Any]) -> dict[str, Any]:
    row["actions"] = _parse_actions(row.get("actions"))
    row["metrics"] = _parse_metrics(row.get("metrics"))
    row["dedup"] = {
        "before": _safe_score(row.pop("dedup_before", 0)),
        "after": _safe_score(row.pop("dedup_after", 0)),
        "duplicates": _safe_score(row.pop("dedup_duplicates", 0)),
    }
    row["publish_result"] = {
        "status": row.pop("publish_status", None),
        "detail": row.pop("publish_detail", None),
        "message": row.get("message"),
    }
    return row


def _parse_actions(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not value:
        return []
    try:
        import json

        parsed = json.loads(str(value))
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except Exception:
        pass
    return []


def _parse_metrics(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _serialize_embedding(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    try:
        return json.dumps([float(item) for item in value], ensure_ascii=False)
    except (TypeError, ValueError):
        return ""


def _deserialize_embedding(value: Any) -> list[float]:
    if not value:
        return []
    if isinstance(value, list):
        try:
            return [float(item) for item in value]
        except (TypeError, ValueError):
            return []
    try:
        parsed = json.loads(str(value))
        if isinstance(parsed, list):
            return [float(item) for item in parsed]
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return []


def _cutoff_iso(days: int) -> str:
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 24 * 60 * 60)
    return datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()


def _safe_score(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
