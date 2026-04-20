from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

from app.skills.llm_analyze import analyze_issue

load_dotenv()

logger = logging.getLogger(__name__)

SKILLS_MD_PATH = Path(__file__).resolve().parents[2] / "skills.md"
DEFAULT_JUDGMENT_REFERENCE = """이슈 유형
- event(사건): 실제 발표, 투자, 규제, 인수합병 같은 명확한 사건
- trend(추세): 시장, 기술, 산업의 지속적 변화
- signal(신호): 발언, 분석, 논의, 시장 시사점

영향 범위
- global(글로벌): 글로벌 시장, 정책, 공급망 수준
- regional(지역/국가): 특정 국가, 지역, 산업 수준
- limited(제한적): 영향 범위가 좁은 경우

변화 성격
- concrete_change(실제 변화): 사건, 발표, 정책 등 명확한 변화
- ongoing_shift(진행 중인 변화): 구조적, 지속적 흐름
- commentary(해설/논평): 분석, 설명 중심 콘텐츠

주요 이슈
- major_issue=true: 의사결정과 모니터링이 필요한 이슈
- major_issue=false: 정보성은 있으나 우선 모니터링 대상까지는 아닌 이슈"""


def analyze_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Analyze collected issues with OpenAI and assign summary and importance."""

    if not issues:
        logger.info("Analyzer: input=%s processed=%s", 0, 0)
        return []

    analyzed_results: list[dict[str, Any]] = []
    processed_count = 0
    judgment_reference = _load_judgment_reference_from_skills()

    if OpenAI is None:
        logger.warning("Analyzer client initialization skipped: openai package is unavailable")
        fallback_results = [
            _fallback_result(issue)
            for issue in issues
            if issue.get("content")
        ]
        logger.info("Analyzer: input=%s processed=%s", len(issues), len(fallback_results))
        return fallback_results

    try:
        client = OpenAI()
    except Exception as exc:  # pragma: no cover
        logger.exception("Analyzer client initialization failed: %s", exc)
        fallback_results = [
            _fallback_result(issue)
            for issue in issues
            if issue.get("content")
        ]
        logger.info("Analyzer: input=%s processed=%s", len(issues), len(fallback_results))
        return fallback_results

    for issue in issues:
        if not issue.get("content"):
            logger.debug("Analyzer skipped issue without content: title=%s", issue.get("title", ""))
            continue

        try:
            analyzed = analyze_issue(
                issue,
                judgment_reference=judgment_reference,
                client=client,
            )
            result = {
                "title": issue.get("title", ""),
                "url": issue.get("url", ""),
                "content": issue.get("content", ""),
                "source_type": issue.get("source_type", ""),
                "summary": analyzed["summary"],
                "score": analyzed["score"],
                "reason": analyzed["reason"],
                "is_recent": analyzed["is_recent"],
                "issue_type": analyzed["issue_type"],
                "impact_scope": analyzed["impact_scope"],
                "change_nature": analyzed["change_nature"],
                "major_issue": analyzed["major_issue"],
                "published_at": issue.get("published_at", ""),
                "source": issue.get("source", ""),
            }
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


def _fallback_result(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": issue.get("title", ""),
        "url": issue.get("url", ""),
        "content": issue.get("content", ""),
        "source_type": issue.get("source_type", ""),
        "summary": "N/A",
        "score": 0,
        "reason": "outdated_or_uncertain",
        "is_recent": False,
        "issue_type": "signal",
        "impact_scope": "limited",
        "change_nature": "commentary",
        "major_issue": False,
        "published_at": issue.get("published_at", ""),
        "source": issue.get("source", ""),
    }


def _load_judgment_reference_from_skills() -> str:
    try:
        content = SKILLS_MD_PATH.read_text(encoding="utf-8")
        match = re.search(
            r"<!-- analyzer_field_reference:start -->\s*```text\s*(.*?)\s*```\s*<!-- analyzer_field_reference:end -->",
            content,
            flags=re.DOTALL,
        )
        if not match:
            return DEFAULT_JUDGMENT_REFERENCE
        reference = match.group(1).strip()
        return reference or DEFAULT_JUDGMENT_REFERENCE
    except Exception:
        logger.exception("Analyzer judgment reference load failed, using default")
        return DEFAULT_JUDGMENT_REFERENCE


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
