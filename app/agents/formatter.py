from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


def format_issues(issues: list[dict[str, Any]]) -> str:
    filtered = [issue for issue in issues if issue.get("status") == "OK"]
    selected = sorted(filtered, key=lambda item: item.get("score", 0), reverse=True)

    logger.info("Formatter: input=%s output=%s", len(issues), len(selected))

    if not selected:
        return "No important issues found"

    blocks = ["🔥 [AI Issue Report]\n"]
    for index, issue in enumerate(selected, start=1):
        emoji = NUMBER_EMOJIS[index - 1] if index - 1 < len(NUMBER_EMOJIS) else f"{index}."
        block = (
            f"{emoji} 제목: {issue.get('title', 'N/A')}\n"
            f"📝 요약: {issue.get('summary', 'N/A')}\n"
            f"📊 중요도: {issue.get('score', 0)}\n"
            f"💬 이유: {issue.get('reason', 'N/A')}\n"
            f"🔗 관련링크: {issue.get('url', 'N/A')}"
        )
        blocks.append(block)

    return "\n\n---\n\n".join(blocks)


class FormatterAgent:
    def format(self, issues: list[dict[str, Any]]) -> dict[str, Any]:
        return {"text": format_issues(issues), "issues": issues}
