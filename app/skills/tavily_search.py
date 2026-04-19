from __future__ import annotations

import os
from typing import Any


def search_issues(query: str) -> list[dict[str, Any]]:
    """Stub search implementation that simulates external issue collection."""

    api_key = os.getenv("TAVILY_API_KEY", "")
    source = "tavily" if api_key else "mock"
    return [
        {
            "title": f"{query} 관련 실시간 이슈",
            "summary": "외부 검색 API 대신 기본 더미 데이터를 반환합니다.",
            "source": source,
            "url": "https://example.com/issues/1",
        }
    ]
