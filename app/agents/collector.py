from __future__ import annotations

from app.skills.tavily_search import search_issues


class CollectorAgent:
    def collect(self, query: str) -> list[dict]:
        return search_issues(query=query)
