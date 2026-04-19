from __future__ import annotations


class ValidatorAgent:
    def validate(self, issues: list[dict]) -> list[dict]:
        valid_issues: list[dict] = []
        for issue in issues:
            if issue.get("title") and issue.get("url"):
                issue["validated"] = True
                valid_issues.append(issue)
        return valid_issues
