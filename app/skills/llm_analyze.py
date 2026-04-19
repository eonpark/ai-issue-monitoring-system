from __future__ import annotations

import os
from typing import Any


def analyze_issue(issue: dict[str, Any]) -> dict[str, Any]:
    """Stub analysis implementation that can later call an LLM."""

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    has_api_key = bool(os.getenv("OPENAI_API_KEY"))
    sentiment = "neutral"
    priority = "medium"

    return {
        **issue,
        "analysis_model": model,
        "analysis_mode": "live" if has_api_key else "mock",
        "sentiment": sentiment,
        "priority": priority,
        "insight": f"'{issue['title']}' 이슈는 모니터링이 필요한 상태입니다.",
    }
