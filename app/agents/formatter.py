from __future__ import annotations


class FormatterAgent:
    def format(self, issues: list[dict]) -> dict:
        lines = ["실시간 이슈 분석 결과"]
        for index, issue in enumerate(issues, start=1):
            lines.append(
                f"{index}. {issue['title']} | priority={issue.get('priority')} | sentiment={issue.get('sentiment')}"
            )
        return {"text": "\n".join(lines), "issues": issues}
