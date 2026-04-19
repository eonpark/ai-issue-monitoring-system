from __future__ import annotations

import json
import logging
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.4-mini"
MAX_ANALYZE_ITEMS = 10


def analyze_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Analyze collected issues with OpenAI and assign summary and importance."""

    if not issues:
        logger.info("Analyzer: input=%s processed=%s", 0, 0)
        return []

    limited_issues = issues[:MAX_ANALYZE_ITEMS]
    analyzed_results: list[dict[str, Any]] = []
    processed_count = 0

    try:
        client = OpenAI()
    except Exception as exc:  # pragma: no cover
        logger.exception("Analyzer client initialization failed: %s", exc)
        fallback_results = [
            _fallback_result(issue, reason="parse_error")
            for issue in limited_issues
            if issue.get("content")
        ]
        logger.info("Analyzer: input=%s processed=%s", len(issues), len(fallback_results))
        return fallback_results

    for issue in limited_issues:
        if not issue.get("content"):
            logger.debug("Analyzer skipped issue without content: title=%s", issue.get("title", ""))
            continue

        try:
            result = _analyze_single_issue(client, issue)
        except Exception as exc:  # pragma: no cover
            logger.exception("Analyzer issue failed: title=%s error=%s", issue.get("title", ""), exc)
            result = _fallback_result(issue, reason="parse_error")

        analyzed_results.append(result)
        processed_count += 1

    logger.info("Analyzer: input=%s processed=%s", len(issues), processed_count)
    logger.debug("Analyzer results: %s", analyzed_results)
    return analyzed_results


class AnalyzerAgent:
    def analyze(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return analyze_issues(issues)


def _analyze_single_issue(client: OpenAI, issue: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "You are an issue analysis engine.\n"
        "Analyze the following issue and return JSON only.\n\n"
        "Requirements:\n"
        "- Summarize only the core news in 2 to 3 short lines.\n"
        "- Score must be an integer from 0 to 100.\n"
        "- Judge importance using these criteria:\n"
        "  1. Global impact\n"
        "  2. Economic or technology impact\n"
        "  3. Urgency, including whether it appears to be breaking news\n"
        "- Return valid JSON with keys: summary, score, reason\n\n"
        f"Title: {issue.get('title', '')}\n"
        f"Content: {issue.get('content', '')}\n"
        f"URL: {issue.get('url', '')}\n"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You produce strict JSON for issue analysis. "
                    "Never include markdown or extra text."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)

    summary = str(parsed.get("summary", "N/A")).strip() or "N/A"
    reason = str(parsed.get("reason", "parse_error")).strip() or "parse_error"
    score = _normalize_score(parsed.get("score"))

    return {
        "title": issue.get("title", ""),
        "url": issue.get("url", ""),
        "summary": summary,
        "score": score,
        "reason": reason,
    }


def _normalize_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, score))


def _fallback_result(issue: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "title": issue.get("title", ""),
        "url": issue.get("url", ""),
        "summary": "N/A",
        "score": 0,
        "reason": reason,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    sample_issues = [
        {
            "title": "Global AI chip demand surges",
            "content": (
                "Major cloud providers increased AI infrastructure spending after a sharp rise "
                "in enterprise demand for model training and inference capacity."
            ),
            "url": "https://example.com/ai-chip-demand",
        },
        {
            "title": "Central bank warns on tech-led market volatility",
            "content": (
                "Officials said rapid capital inflows into AI and semiconductor stocks could "
                "increase short-term volatility across global equity markets."
            ),
            "url": "https://example.com/market-volatility",
        },
    ]
    print(json.dumps(analyze_issues(sample_issues), ensure_ascii=False, indent=2))
