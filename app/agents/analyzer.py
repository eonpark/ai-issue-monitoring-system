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
            _fallback_result(issue)
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
            result = _fallback_result(issue)

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
        "당신은 주요 이슈 분석 엔진이다.\n"
        "아래 이슈를 분석하고 JSON만 반환하라.\n\n"
        "반드시 지킬 요구사항:\n"
        "- 제목은 번역하지 않는다. 제목 원문은 입력으로만 참고한다.\n"
        "- summary는 반드시 한국어로 작성한다.\n"
        "- reason도 반드시 한국어로 작성한다.\n"
        "- summary는 뉴스 핵심만 2~3줄로 간결하게 요약한다.\n"
        "- score는 반드시 0~100 사이 정수로 반환한다.\n"
        "- is_recent는 true 또는 false 로 반환한다.\n"
        "- issue_type은 반드시 event, trend, signal 중 하나로 반환한다.\n"
        "- 이슈를 3가지 타입으로 분류하라:\n"
        "  1. event: 실제 사건, 정책 발표, 투자, 규제\n"
        "  2. trend: 지속적인 흐름, 경제 구조 변화, 기술 변화\n"
        "  3. signal: 인터뷰, 발언, 논의, 분석, 시장 신호\n"
        "- 점수 기준은 다음 밴드를 따른다:\n"
        "  1. event: 70~100\n"
        "  2. trend: 50~80\n"
        "  3. signal: 40~70\n"
        "- 중요도 판단 기준은 다음 3가지다:\n"
        "  1. 글로벌 영향력\n"
        "  2. 경제/기술 영향\n"
        "  3. 긴급성, 즉 breaking 여부\n"
        "- 이 콘텐츠가 단순 뉴스가 아니라, 중요한 발언, 정책 방향, 시장 신호일 경우 signal로 판단하고 점수를 낮추지 마라.\n"
        "- breaking 여부는 점수에 일부만 반영하라.\n"
        "- 시간 검증 단계를 반드시 수행한다.\n"
        "- 이 콘텐츠가 최근 이슈인지 판단하라.\n"
        "- 이 정보가 최근 발생한 사건인지 판단하라. 단순 분석/보고서/과거 글이면 중요도를 낮게 평가하라.\n"
        "- 오래된 정보(1주 이상)면 score를 0~30으로 제한하라.\n"
        "- 날짜가 불명확하면 낮은 점수를 부여하라.\n"
        "- 오래된 콘텐츠라도 의미 있는 분석이면 score 40 이상 가능하다.\n"
        "- 입력 데이터 외 내용 생성 금지.\n"
        "- 추측 금지.\n"
        "- 기사 내용 기반으로만 작성하라.\n"
        "- 반환 키는 summary, score, reason, is_recent, issue_type 만 포함한다.\n\n"
        f"Title (keep original, do not translate): {issue.get('title', '')}\n"
        f"Content: {issue.get('content', '')}\n"
        f"URL: {issue.get('url', '')}\n"
        f"Published at: {issue.get('published_at', '')}\n"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 이슈 분석용 strict JSON만 반환한다. "
                    "마크다운, 설명, 코드블록, 추가 텍스트를 출력하지 않는다. "
                    "summary와 reason은 반드시 한국어여야 한다. "
                    "입력에 없는 사실을 추측하거나 보완하지 않는다."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)

    summary = str(parsed.get("summary", "N/A")).strip() or "N/A"
    reason = str(parsed.get("reason", "outdated_or_uncertain")).strip() or "outdated_or_uncertain"
    score = _normalize_score(parsed.get("score"))
    is_recent = bool(parsed.get("is_recent", False))
    issue_type = _normalize_issue_type(parsed.get("issue_type"))

    return {
        "title": issue.get("title", ""),
        "url": issue.get("url", ""),
        "summary": summary,
        "score": score,
        "reason": reason,
        "is_recent": is_recent,
        "issue_type": issue_type,
    }


def _normalize_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, score))


def _normalize_issue_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"event", "trend", "signal"}:
        return normalized
    return "signal"


def _fallback_result(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": issue.get("title", ""),
        "url": issue.get("url", ""),
        "summary": "N/A",
        "score": 0,
        "reason": "outdated_or_uncertain",
        "is_recent": False,
        "issue_type": "signal",
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
