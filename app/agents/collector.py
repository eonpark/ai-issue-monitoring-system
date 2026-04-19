from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
DEFAULT_QUERIES = ["AI news"]


def collect_issues() -> list[dict[str, Any]]:
    """Collect issues from Tavily REST API and normalize the results."""

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        logger.info("Collector: queries=%s success=%s collected=%s", len(DEFAULT_QUERIES), 0, 0)
        return []

    issues: list[dict[str, Any]] = []
    success_count = 0
    total_queries = len(DEFAULT_QUERIES)

    for query in DEFAULT_QUERIES:
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": False,
            "max_results": 5,
        }

        try:
            response = requests.post(TAVILY_API_URL, json=payload, timeout=20)
            response.raise_for_status()
            response_json = response.json()
            results = response_json.get("results", [])
            success_count += 1
        except Exception:  # pragma: no cover
            logger.exception("Collector query failed: query=%s", query)
            continue

        logger.debug(
            "Collector query result: query=%s results=%s request_id=%s response_time=%s",
            query,
            len(results),
            response_json.get("request_id"),
            response_json.get("response_time"),
        )

        issues.extend(_normalize_results(results))

    logger.info(
        "Collector: queries=%s success=%s collected=%s",
        total_queries,
        success_count,
        len(issues),
    )
    logger.debug("Collector normalized issues: %s", issues)
    return issues


def _normalize_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for item in results:
        url = item.get("url", "")
        normalized.append(
            {
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "url": url,
                "source": _extract_domain(url),
                "published_at": item.get("published_date", "") or item.get("published_at", ""),
            }
        )
    return normalized


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
