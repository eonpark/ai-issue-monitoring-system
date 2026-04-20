from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

load_dotenv()

logger = logging.getLogger(__name__)
AUDIT_MODEL_NAME = "gpt-5.4-mini"
FRESHNESS_DAYS = 14

THRESHOLDS = {
    "event": 60,
    "trend": 50,
    "signal": 45,
}
OK_REASONS = {
    "event": "정책 방향성 이슈",
    "trend": "시장 트렌드 신호",
    "signal": "전문가 발언 기반 이슈",
}
NO_OK_REASON = "중요도 낮음 또는 영향도 제한적"
MAJOR_ISSUE_REASON = "주요 이슈 정의를 충족하지 않음"


def validate_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate analyzed issues and mark whether they should be reported."""

    if not issues:
        logger.info("Validator: total=%s ok=%s no_ok=%s", 0, 0, 0)
        return []

    try:
        validated: list[dict[str, Any]] = []
        ok_count = 0
        no_ok_count = 0

        for issue in issues:
            score = _safe_score(issue.get("score"))
            issue_type = _normalize_issue_type(issue.get("issue_type"))
            threshold = THRESHOLDS[issue_type]
            major_issue = bool(issue.get("major_issue", False))
            impact_scope = _normalize_impact_scope(issue.get("impact_scope"))
            change_nature = _normalize_change_nature(issue.get("change_nature"))
            audit = _audit_issue(issue)
            meets_definition = _meets_major_issue_definition(
                major_issue=major_issue,
                impact_scope=impact_scope,
                change_nature=change_nature,
            )
            is_ok = (
                score >= threshold
                and meets_definition
                and audit["source_verified"]
                and audit["content_match"]
            )
            validated_issue = {
                **issue,
                "issue_type": issue_type,
                "score": score,
                "impact_scope": impact_scope,
                "change_nature": change_nature,
                "major_issue": major_issue,
                "audited_published_at": audit.get("published_at", ""),
                "source_verified": audit["source_verified"],
                "content_match": audit["content_match"],
                "audit_reason": audit["audit_reason"],
                "status": "OK" if is_ok else "NO_OK",
                "validated": is_ok,
                "validation_reason": (
                    OK_REASONS[issue_type]
                    if is_ok
                    else _build_no_ok_reason(
                        major_issue=major_issue,
                        meets_definition=meets_definition,
                        impact_scope=impact_scope,
                        change_nature=change_nature,
                        audit_reason=audit["audit_reason"],
                        source_verified=audit["source_verified"],
                        content_match=audit["content_match"],
                    )
                ),
            }
            validated.append(validated_issue)

            if is_ok:
                ok_count += 1
            else:
                no_ok_count += 1

        logger.info("Validator: total=%s ok=%s no_ok=%s", len(validated), ok_count, no_ok_count)
        logger.debug("Validator output: %s", validated)
        return validated
    except Exception as exc:  # pragma: no cover
        logger.exception("Validator failed: %s", exc)
        return []


class ValidatorAgent:
    def validate(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return validate_issues(issues)


def _safe_score(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_issue_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in THRESHOLDS:
        return normalized
    return "signal"


def _normalize_impact_scope(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"global", "regional", "limited"}:
        return normalized
    return "limited"


def _normalize_change_nature(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"concrete_change", "ongoing_shift", "commentary"}:
        return normalized
    return "commentary"


def _meets_major_issue_definition(
    major_issue: bool,
    impact_scope: str,
    change_nature: str,
) -> bool:
    if not major_issue:
        return False
    if change_nature == "commentary" and impact_scope == "limited":
        return False
    return True


def _build_no_ok_reason(
    major_issue: bool,
    meets_definition: bool,
    impact_scope: str,
    change_nature: str,
    audit_reason: str,
    source_verified: bool,
    content_match: bool,
) -> str:
    if not source_verified:
        if audit_reason == "missing_url":
            return "링크 정보가 없는 이슈"
        if audit_reason == "missing_publication_date":
            return "링크에서 발행일을 확인할 수 없는 이슈"
        if audit_reason == "outdated_source":
            return "최신 이슈 기준을 벗어난 오래된 이슈"
        if audit_reason == "insufficient_fetched_content":
            return "링크 본문을 충분히 확인할 수 없는 이슈"
        if audit_reason == "generic_or_empty_source":
            return "링크가 실제 본문이 아닌 일반 페이지/허브로 보이는 이슈"
        return "링크 원문 검증에 실패한 이슈"
    if not content_match:
        return "원문 내용과 요약이 충분히 일치하지 않는 이슈"
    if not major_issue:
        return MAJOR_ISSUE_REASON
    if impact_scope == "limited" and change_nature != "concrete_change":
        return "영향 범위가 제한적인 이슈"
    if change_nature == "commentary" and impact_scope == "limited":
        return "변화의 실체가 약한 해설성 이슈"
    if not meets_definition:
        return MAJOR_ISSUE_REASON
    return NO_OK_REASON


def _audit_issue(issue: dict[str, Any]) -> dict[str, Any]:
    url = str(issue.get("url", "")).strip()
    collected_content = str(issue.get("content", "")).strip()
    summary = str(issue.get("summary", "")).strip()
    reason = str(issue.get("reason", "")).strip()
    title = str(issue.get("title", "")).strip()
    issue_type = _normalize_issue_type(issue.get("issue_type"))

    if not url:
        return {
            "source_verified": False,
            "content_match": False,
            "audit_reason": "missing_url",
        }

    fetch_result = _fetch_page_text(url)
    fetched_content = fetch_result["content"]
    fetched_html = fetch_result["html"]
    final_url = fetch_result["final_url"] or url
    published_at = _extract_publication_date(
        final_url=final_url,
        fetched_html=fetched_html,
        fetched_content=fetched_content,
        fallback_published_at=str(issue.get("published_at", "")).strip(),
    )
    if not published_at:
        if issue_type in {"trend", "signal"}:
            published_at = str(issue.get("published_at", "")).strip()
        else:
            return {
                "published_at": "",
                "source_verified": False,
                "content_match": False,
                "audit_reason": "missing_publication_date",
            }
    normalized_published_at = _normalize_date(published_at)
    if normalized_published_at and _is_outdated(normalized_published_at):
        if issue_type == "event":
            return {
                "published_at": normalized_published_at,
                "source_verified": False,
                "content_match": False,
                "audit_reason": "outdated_source",
            }
    elif issue_type == "event":
        return {
            "published_at": "",
            "source_verified": False,
            "content_match": False,
            "audit_reason": "missing_publication_date",
        }
    if len(fetched_content) < 120:
        return {
            "published_at": normalized_published_at,
            "source_verified": False,
            "content_match": False,
            "audit_reason": "insufficient_fetched_content",
        }

    if _looks_generic_landing_page(final_url, fetched_content):
        return {
            "published_at": normalized_published_at,
            "source_verified": False,
            "content_match": False,
            "audit_reason": "generic_or_empty_source",
        }

    llm_audit = _llm_audit_issue(
        title=title,
        summary=summary,
        reason=reason,
        url=final_url,
        fetched_content=fetched_content,
        collected_content=collected_content,
    )
    llm_audit["published_at"] = normalized_published_at
    return llm_audit


def _fetch_page_text(url: str) -> dict[str, str]:
    try:
        response = requests.get(
            url,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 AI-Issue-Monitor/1.0"},
        )
        response.raise_for_status()
        html = response.text
    except Exception:
        return {"content": "", "html": "", "final_url": ""}

    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return {"content": text[:12000], "html": html[:20000], "final_url": response.url}


def _llm_audit_issue(
    title: str,
    summary: str,
    reason: str,
    url: str,
    fetched_content: str,
    collected_content: str,
) -> dict[str, Any]:
    if OpenAI is None:
        parsed = {}
        source_verified = bool(parsed.get("source_verified", False))
        content_match = bool(parsed.get("content_match", False))
        audit_reason = str(parsed.get("audit_reason", "")).strip().lower()
        if not audit_reason:
            keyword_hits = _count_keyword_hits(title=title, summary=summary, source_text=fetched_content)
            content_match = keyword_hits >= 3
            source_verified = content_match
            audit_reason = "matched_source_content" if content_match else "content_mismatch"
        normalized_reason_map = {
            "homepage_or_listing_page": "generic_or_empty_source",
            "generic_page": "generic_or_empty_source",
            "hub_page": "generic_or_empty_source",
            "landing_page": "generic_or_empty_source",
            "listing_page": "generic_or_empty_source",
            "content_mismatch": "content_mismatch",
            "matched_source_content": "matched_source_content",
            "relevant_source_content": "matched_source_content",
        }
        return {
            "published_at": "",
            "source_verified": source_verified,
            "content_match": content_match,
            "audit_reason": normalized_reason_map.get(audit_reason, audit_reason or "content_mismatch"),
        }

    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model=AUDIT_MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 링크 근거 감사기다. "
                        "반드시 JSON만 반환한다. "
                        "입력에 없는 사실을 추측하지 않는다."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "아래 링크와 본문을 보고, 이 페이지가 실제로 이 이슈를 뒷받침하는지 감사하라.\n"
                        "평가 기준:\n"
                        "1. 링크가 실제 관련 문서/기사/보고서/브리핑 본문인지\n"
                        "2. 단순 홈페이지/목록/허브/빈 페이지가 아닌지\n"
                        "3. analyzer의 summary와 reason이 fetched_content의 핵심 내용과 실제로 맞는지\n"
                        "4. 일치하지 않으면 content_match=false로 판단하라\n"
                        "5. 링크가 일반 홈페이지/허브/목록 페이지라면 source_verified=false로 판단하라\n"
                        "반환 키는 source_verified, content_match, audit_reason만 포함한다.\n\n"
                        f"Title: {title}\n"
                        f"URL: {url}\n"
                        f"Analyzer Summary: {summary}\n"
                        f"Analyzer Reason: {reason}\n"
                        f"Collector Content: {collected_content[:4000]}\n"
                        f"Fetched Content: {fetched_content[:8000]}\n"
                    ),
                },
            ],
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
    except Exception:
        parsed = {}

    source_verified = bool(parsed.get("source_verified", False))
    content_match = bool(parsed.get("content_match", False))
    audit_reason = str(parsed.get("audit_reason", "")).strip().lower()

    if not audit_reason:
        keyword_hits = _count_keyword_hits(title=title, summary=summary, source_text=fetched_content)
        content_match = keyword_hits >= 3
        source_verified = content_match
        audit_reason = "matched_source_content" if content_match else "content_mismatch"

    normalized_reason_map = {
        "homepage_or_listing_page": "generic_or_empty_source",
        "generic_page": "generic_or_empty_source",
        "hub_page": "generic_or_empty_source",
        "landing_page": "generic_or_empty_source",
        "listing_page": "generic_or_empty_source",
        "content_mismatch": "content_mismatch",
        "matched_source_content": "matched_source_content",
        "relevant_source_content": "matched_source_content",
    }

    return {
        "published_at": "",
        "source_verified": source_verified,
        "content_match": content_match,
        "audit_reason": normalized_reason_map.get(audit_reason, audit_reason or "content_mismatch"),
    }


def _extract_publication_date(
    final_url: str,
    fetched_html: str,
    fetched_content: str,
    fallback_published_at: str,
) -> str:
    candidates = [
        fallback_published_at.strip(),
        _extract_date_from_html(fetched_html),
        _extract_date_from_contextual_text(fetched_content[:2500]),
        _extract_date_from_url(final_url),
    ]
    for candidate in candidates:
        normalized = _normalize_date(candidate)
        if normalized:
            return normalized
    return ""


def _extract_date_from_html(html: str) -> str:
    if not html:
        return ""

    meta_patterns = [
        r'<meta[^>]+(?:property|name)=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\']og:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\']publish-date["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\']date["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\']datepublished["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pattern in meta_patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    jsonld_blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
        html,
        flags=re.IGNORECASE,
    )
    for block in jsonld_blocks:
        date_match = re.search(
            r'"datePublished"\s*:\s*"([^"]+)"|"dateModified"\s*:\s*"([^"]+)"',
            block,
            flags=re.IGNORECASE,
        )
        if date_match:
            return date_match.group(1) or date_match.group(2) or ""

    time_match = re.search(
        r'<time[^>]+datetime=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if time_match:
        return time_match.group(1)

    return ""


def _extract_date_from_url(text: str) -> str:
    if not text:
        return ""

    patterns = [
        r"/(20\d{2}/\d{1,2}/\d{1,2})(?:/|$)",
        r"/(20\d{2}-\d{1,2}-\d{1,2})(?:/|$)",
        r"/(20\d{2}\.\d{1,2}\.\d{1,2})(?:/|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def _extract_date_from_contextual_text(text: str) -> str:
    if not text:
        return ""

    normalized_text = re.sub(r"\s+", " ", text).strip()
    patterns = [
        r"(?:기사입력|입력|등록|등록시간|송고|송고시간|업데이트|수정|수정시간)\s*[:：]?\s*((?:20\d{2}[./-]\d{1,2}[./-]\d{1,2}|20\d{2}년\s*\d{1,2}월\s*\d{1,2}일)(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
        r"(?:Published|Updated|Posted on|Published on|Last updated)\s*[:：]?\s*((?:20\d{2}[./-]\d{1,2}[./-]\d{1,2}|20\d{2}년\s*\d{1,2}월\s*\d{1,2}일)(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized_text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _normalize_date(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""

    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", cleaned)
    if iso_match:
        cleaned = iso_match.group(1)
    else:
        slash_match = re.search(r"\b(20\d{2}/\d{1,2}/\d{1,2})\b", cleaned)
        if slash_match:
            cleaned = slash_match.group(1)
        else:
            dot_match = re.search(r"\b(20\d{2}\.\d{1,2}\.\d{1,2})\b", cleaned)
            if dot_match:
                cleaned = dot_match.group(1)
            else:
                korean_match = re.search(
                    r"\b(20\d{2}년\s*\d{1,2}월\s*\d{1,2}일)\b",
                    cleaned,
                )
                if korean_match:
                    cleaned = korean_match.group(1)

    iso_like = (
        cleaned.replace("년", "-")
        .replace("월", "-")
        .replace("일", "")
        .replace(".", "-")
        .replace("/", "-")
        .replace(" ", "")
    )
    parts = [part for part in iso_like.split("-") if part]
    if len(parts) < 3:
        return ""

    try:
        parsed = date(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return ""
    return parsed.isoformat()


def _is_outdated(published_at: str) -> bool:
    normalized = _normalize_date(published_at)
    if not normalized:
        return True
    published_date = datetime.strptime(normalized, "%Y-%m-%d").date()
    freshness_threshold = date.today() - timedelta(days=FRESHNESS_DAYS)
    return published_date < freshness_threshold


def _looks_generic_landing_page(url: str, source_text: str) -> bool:
    parsed = urlparse(url)
    generic_path = parsed.path.strip() in {"", "/"}
    generic_markers = [
        "subscribe",
        "all rights reserved",
        "breaking news",
        "latest news",
        "홈",
        "전체기사",
        "로그인",
        "구독",
    ]
    marker_hits = sum(1 for marker in generic_markers if marker.lower() in source_text.lower())
    return generic_path and marker_hits >= 2


def _count_keyword_hits(title: str, summary: str, source_text: str) -> int:
    tokens = _extract_keywords(f"{title} {summary}")
    if not tokens:
        return 0
    lowered_source = source_text.lower()
    hits = 0
    for token in tokens[:8]:
        if token.lower() in lowered_source:
            hits += 1
    return hits


def _extract_keywords(text: str) -> list[str]:
    raw_tokens = re.findall(r"[A-Za-z0-9가-힣]{2,}", text)
    stopwords = {
        "the",
        "and",
        "that",
        "with",
        "this",
        "from",
        "있다",
        "관련",
        "대한",
        "최근",
        "통해",
        "대한민국",
    }
    deduped: list[str] = []
    seen: set[str] = set()
    for token in raw_tokens:
        normalized = token.lower()
        if normalized in stopwords:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(token)
    return deduped
