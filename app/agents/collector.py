from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
QUERY_GROUPS = {
    "news": [
        "South Korea breaking politics economy technology",
        "global breaking economy technology geopolitics",
        "Asia major issues economy security",
    ],
    "event": [
        "AI regulation announcement",
        "startup funding news",
        "company acquisition news",
        "policy change news",
    ],
    "social": [
        "site:twitter.com AI trend",
        "site:reddit.com tech discussion",
        "site:news.ycombinator.com startup",
    ],
}
EXCLUDED_URL_KEYWORDS = ["/news", "/category", "/search", "/tag"]
EXCLUDED_TITLE_KEYWORDS = ["top", "list", "trending", "모음"]
MIN_CONTENT_LENGTH = 100
MAX_RESULTS_PER_QUERY = 5
TIME_RANGE = "week"
DATE_PATTERNS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
]


def collect_issues() -> list[dict[str, Any]]:
    """Collect issues from Tavily REST API and normalize the results."""

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    total_queries = sum(len(queries) for queries in QUERY_GROUPS.values())
    if not api_key:
        logger.info("Collector: queries=%s success=%s collected=%s", total_queries, 0, 0)
        return []

    issues: list[dict[str, Any]] = []
    success_count = 0

    for source_type, queries in QUERY_GROUPS.items():
        for query in queries:
            payload = {
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "include_answer": False,
                "max_results": MAX_RESULTS_PER_QUERY,
                "time_range": TIME_RANGE,
            }

            try:
                response = requests.post(TAVILY_API_URL, json=payload, timeout=20)
                response.raise_for_status()
                response_json = response.json()
                results = response_json.get("results", [])
                success_count += 1
            except Exception:  # pragma: no cover
                logger.exception("Collector query failed: source_type=%s query=%s", source_type, query)
                continue

            logger.debug(
                "Collector query result: source_type=%s query=%s results=%s request_id=%s response_time=%s",
                source_type,
                query,
                len(results),
                response_json.get("request_id"),
                response_json.get("response_time"),
            )

            issues.extend(_normalize_results(results, source_type=source_type))

    deduped_issues = _deduplicate_issues(issues)
    fresh_issues = _filter_fresh_issues(deduped_issues)
    logger.info("Fresh filter: before=%s after=%s", len(deduped_issues), len(fresh_issues))
    filtered_issues = _filter_article_issues(fresh_issues)
    logger.info("Collector filtered: before=%s after=%s", len(fresh_issues), len(filtered_issues))
    logger.info(
        "Collector: queries=%s success=%s collected=%s",
        total_queries,
        success_count,
        len(filtered_issues),
    )
    logger.debug("Collector normalized issues: %s", filtered_issues)
    return filtered_issues


def _normalize_results(results: list[dict[str, Any]], source_type: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in results:
        url = item.get("url", "")
        content = item.get("content", "")
        published_at = _extract_published_date(
            item.get("published_date", "") or item.get("published_at", ""),
            content,
        )
        normalized.append(
            {
                "title": item.get("title", ""),
                "content": content,
                "url": url,
                "source": _extract_domain(url),
                "source_type": source_type,
                "published_at": published_at,
            }
        )
    return normalized


def _deduplicate_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue in issues:
        url = str(issue.get("url", "")).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(issue)
    return deduped


def _filter_article_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for issue in issues:
        url = str(issue.get("url", "")).lower()
        title = str(issue.get("title", "")).lower()
        content = str(issue.get("content", "")).strip()

        if any(keyword in url for keyword in EXCLUDED_URL_KEYWORDS):
            continue
        if len(content) <= MIN_CONTENT_LENGTH:
            continue
        if any(keyword in title for keyword in EXCLUDED_TITLE_KEYWORDS):
            continue

        filtered.append(issue)
    return filtered


def _filter_fresh_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fresh: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=7)

    for issue in issues:
        published_at = str(issue.get("published_at", "")).strip()
        if not published_at:
            continue

        try:
            published_date = datetime.strptime(published_at, "%Y-%m-%d").date()
        except ValueError:
            continue

        if published_date >= cutoff:
            fresh.append(issue)

    return fresh


def _extract_published_date(raw_date: str, content: str) -> str:
    candidate = str(raw_date).strip()
    parsed = _parse_date(candidate)
    if parsed:
        return parsed

    content_text = str(content)
    regex_candidates = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{4}/\d{2}/\d{2}\b",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}, \d{4}\b",
        r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b",
    ]
    for pattern in regex_candidates:
        match = re.search(pattern, content_text, flags=re.IGNORECASE)
        if not match:
            continue
        parsed = _parse_date(match.group(0))
        if parsed:
            return parsed

    return ""


def _parse_date(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""

    cleaned = cleaned.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned).date().isoformat()
    except ValueError:
        pass

    for pattern in DATE_PATTERNS:
        try:
            return datetime.strptime(cleaned, pattern).date().isoformat()
        except ValueError:
            continue
    return ""


class CollectorAgent:
    def collect(self, query: str | None = None) -> list[dict[str, Any]]:
        return collect_issues()


def _extract_domain(url: str) -> str:
    if not url:
        return ""
    return urlparse(url).netloc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    collected = collect_issues()
    logger.info("Collector main finished: collected=%s", len(collected))
