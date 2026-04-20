from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
DATE_PATTERNS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
]


def search_issues(
    query: str,
    *,
    source_type: str,
    region: str,
    time_range: str = "week",
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Search Tavily and return normalized issue candidates."""

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    normalized_query = str(query).strip()
    if not api_key or not normalized_query:
        return []

    payload = {
        "api_key": api_key,
        "query": normalized_query,
        "search_depth": "basic",
        "include_answer": False,
        "max_results": max_results,
        "time_range": time_range,
    }

    try:
        response = requests.post(TAVILY_API_URL, json=payload, timeout=20)
        response.raise_for_status()
        response_json = response.json()
        results = response_json.get("results", [])
    except Exception:  # pragma: no cover
        logger.exception(
            "Tavily search failed: region=%s source_type=%s query=%s",
            region,
            source_type,
            normalized_query,
        )
        return []

    logger.debug(
        "Tavily search result: region=%s source_type=%s query=%s results=%s request_id=%s response_time=%s",
        region,
        source_type,
        normalized_query,
        len(results),
        response_json.get("request_id"),
        response_json.get("response_time"),
    )
    return _normalize_results(results, source_type=source_type, region=region)


def _normalize_results(results: list[dict[str, Any]], source_type: str, region: str) -> list[dict[str, Any]]:
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
                "region": region,
                "published_at": published_at,
            }
        )
    return normalized


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
    if not value:
        return ""
    normalized = value.strip()
    if "T" in normalized:
        normalized = normalized.split("T", 1)[0]

    for pattern in DATE_PATTERNS:
        try:
            parsed = datetime.strptime(normalized, pattern)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""
