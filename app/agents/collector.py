from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
SKILLS_MD_PATH = Path(__file__).resolve().parents[2] / "skills.md"
DEFAULT_QUERY_GROUPS = {
    "domestic": {
        "news": [
            "한국 주요 이슈 정책 경제 기술 산업",
            "국내 정책 변화 시장 기술 기업",
            "site:yna.co.kr OR site:hankyung.com OR site:mk.co.kr OR site:sedaily.com 한국 정책 경제 기술 기업",
        ],
        "event": [
            "국내 규제 발표 기술 정책",
            "한국 스타트업 투자 유치 인수합병",
            "국내 기업 실적 투자 공급망 발표",
        ],
        "social": [
            "site:news.ycombinator.com Korea startup policy",
            "site:reddit.com Korea economy technology policy",
        ],
    },
    "global": {
        "news": [
            "global major issues policy market technology companies",
            "world economy technology regulation supply chain",
            "site:reuters.com OR site:bloomberg.com OR site:ft.com OR site:wsj.com global policy market technology",
        ],
        "event": [
            "AI regulation announcement",
            "startup funding acquisition announcement",
            "policy change market guidance",
            "company earnings supply chain announcement",
        ],
        "social": [
            "site:twitter.com policy market technology signal",
            "site:reddit.com tech policy discussion",
            "site:news.ycombinator.com startup market regulation",
        ],
    },
}
MAX_RESULTS_PER_QUERY = 5
TIME_RANGE = "week"
MAX_PER_REGION = 10
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
    query_groups = _load_query_groups_from_skills()
    total_queries = sum(
        len(queries)
        for region_groups in query_groups.values()
        for queries in region_groups.values()
    )
    if not api_key:
        logger.info("Collector: queries=%s success=%s collected=%s", total_queries, 0, 0)
        return []

    issues_by_region: dict[str, list[dict[str, Any]]] = {"domestic": [], "global": []}
    success_count = 0

    for region, region_groups in query_groups.items():
        region_issues: list[dict[str, Any]] = []
        for source_type, queries in region_groups.items():
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
                    logger.exception(
                        "Collector query failed: region=%s source_type=%s query=%s",
                        region,
                        source_type,
                        query,
                    )
                    continue

                logger.debug(
                    "Collector query result: region=%s source_type=%s query=%s results=%s request_id=%s response_time=%s",
                    region,
                    source_type,
                    query,
                    len(results),
                    response_json.get("request_id"),
                    response_json.get("response_time"),
                )

                region_issues.extend(
                    _normalize_results(results, source_type=source_type, region=region)
                )
        issues_by_region[region] = _keep_minimum_viable_issues(_deduplicate_issues(region_issues))[:MAX_PER_REGION]

    balanced_issues = _balance_regions(
        domestic_issues=issues_by_region["domestic"],
        global_issues=issues_by_region["global"],
    )
    normalized_issues = _keep_minimum_viable_issues(_deduplicate_issues(balanced_issues))
    logger.info(
        "Collector normalized: domestic=%s global=%s balanced=%s",
        len(issues_by_region["domestic"]),
        len(issues_by_region["global"]),
        len(normalized_issues),
    )
    logger.info(
        "Collector: queries=%s success=%s collected=%s",
        total_queries,
        success_count,
        len(normalized_issues),
    )
    logger.debug("Collector normalized issues: %s", normalized_issues)
    return normalized_issues


def _load_query_groups_from_skills() -> dict[str, dict[str, list[str]]]:
    try:
        content = SKILLS_MD_PATH.read_text(encoding="utf-8")
        match = re.search(
            r"<!-- collector_query_config:start -->\s*```json\s*(\{.*?\})\s*```\s*<!-- collector_query_config:end -->",
            content,
            flags=re.DOTALL,
        )
        if not match:
            logger.info("Collector query config: source=default")
            return DEFAULT_QUERY_GROUPS

        parsed = json.loads(match.group(1))
        validated = _validate_query_groups(parsed)
        logger.info("Collector query config: source=skills.md")
        return validated
    except Exception:
        logger.exception("Collector query config load failed, using default")
        return DEFAULT_QUERY_GROUPS


def _validate_query_groups(raw: Any) -> dict[str, dict[str, list[str]]]:
    validated: dict[str, dict[str, list[str]]] = {}
    for region in ("domestic", "global"):
        region_groups = raw.get(region, {}) if isinstance(raw, dict) else {}
        validated[region] = {}
        for source_type in ("news", "event", "social"):
            queries = region_groups.get(source_type, []) if isinstance(region_groups, dict) else []
            if not isinstance(queries, list):
                queries = []
            validated[region][source_type] = [
                str(query).strip() for query in queries if str(query).strip()
            ]
    return validated


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


def _keep_minimum_viable_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for issue in issues:
        if not str(issue.get("url", "")).strip():
            continue
        if not str(issue.get("title", "")).strip():
            continue
        kept.append(
            {
                "title": str(issue.get("title", "")).strip(),
                "content": str(issue.get("content", "")).strip(),
                "url": str(issue.get("url", "")).strip(),
                "source": str(issue.get("source", "")).strip(),
                "source_type": str(issue.get("source_type", "")).strip(),
                "region": str(issue.get("region", "")).strip(),
                "published_at": str(issue.get("published_at", "")).strip(),
            }
        )
    return kept


def _balance_regions(
    domestic_issues: list[dict[str, Any]],
    global_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    balanced: list[dict[str, Any]] = []
    max_len = max(len(domestic_issues), len(global_issues))
    for index in range(max_len):
        if index < len(domestic_issues):
            balanced.append(domestic_issues[index])
        if index < len(global_issues):
            balanced.append(global_issues[index])
    return balanced


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
