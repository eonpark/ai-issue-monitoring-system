from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

THRESHOLDS = {
    "event": 60,
    "trend": 50,
    "signal": 45,
}
OK_REASONS = {
    "event": "정책 방향성 이슈",
    "trend": "시장 트렌드 신호",
    "signal": "전문가 발언 기반 이슈",
}
NO_OK_REASON = "중요도 낮음 또는 영향도 제한적"


def validate_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate analyzed issues and mark whether they should be reported."""

    if not issues:
        logger.info("Validator: total=%s ok=%s no_ok=%s", 0, 0, 0)
        return []

    try:
        validated: list[dict[str, Any]] = []
        ok_count = 0
        no_ok_count = 0

        for issue in issues:
            score = _safe_score(issue.get("score"))
            issue_type = _normalize_issue_type(issue.get("issue_type"))
            threshold = THRESHOLDS[issue_type]
            is_ok = score >= threshold
            validated_issue = {
                **issue,
                "issue_type": issue_type,
                "score": score,
                "status": "OK" if is_ok else "NO_OK",
                "validated": is_ok,
                "validation_reason": OK_REASONS[issue_type] if is_ok else NO_OK_REASON,
            }
            validated.append(validated_issue)

            if is_ok:
                ok_count += 1
            else:
                no_ok_count += 1

        logger.info("Validator: total=%s ok=%s no_ok=%s", len(validated), ok_count, no_ok_count)
        logger.debug("Validator output: %s", validated)
        return validated
    except Exception as exc:  # pragma: no cover
        logger.exception("Validator failed: %s", exc)
        return []


class ValidatorAgent:
    def validate(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return validate_issues(issues)


def _safe_score(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_issue_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in THRESHOLDS:
        return normalized
    return "signal"
