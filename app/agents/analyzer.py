from __future__ import annotations

from app.skills.llm_analyze import analyze_issue


class AnalyzerAgent:
    def analyze(self, issues: list[dict]) -> list[dict]:
        return [analyze_issue(issue) for issue in issues]
