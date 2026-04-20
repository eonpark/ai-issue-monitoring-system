from __future__ import annotations

import json
import logging
from typing import Any

from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.4-mini"


def analyze_issue(
    issue: dict[str, Any],
    *,
    judgment_reference: str,
    client: OpenAI | None = None,
) -> dict[str, Any]:
    """Analyze one issue with OpenAI and return normalized fields."""

    if OpenAI is None:
        raise RuntimeError("openai package is unavailable")

    llm_client = client or OpenAI()
    prompt = (
        "당신은 주요 이슈 분석 엔진이다.\n"
        "아래 이슈를 분석하고 JSON만 반환하라.\n\n"
        "판정 필드 정의는 아래 문서 기준을 따른다.\n"
        f"{judgment_reference}\n\n"
        "반드시 지킬 요구사항:\n"
        "- 제목은 번역하지 않는다. 제목 원문은 입력으로만 참고한다.\n"
        "- summary는 반드시 한국어로 작성한다.\n"
        "- reason도 반드시 한국어로 작성한다.\n"
        "- summary는 뉴스 핵심만 2~3줄로 간결하게 요약한다.\n"
        "- score는 반드시 0~100 사이 정수로 반환한다.\n"
        "- is_recent는 true 또는 false 로 반환한다.\n"
        "- issue_type은 반드시 event, trend, signal 중 하나로 반환한다.\n"
        "- major issue 판단을 위해 아래 4가지를 반드시 평가하라:\n"
        "  1. impact_scope: global, regional, limited 중 하나\n"
        "  2. change_nature: concrete_change, ongoing_shift, commentary 중 하나\n"
        "  3. major_issue: true 또는 false\n"
        "- 주요 이슈 정의: 정책, 시장, 기술, 기업 활동의 변화 중에서 한국 또는 글로벌 차원의 의사결정과 모니터링이 필요한 사건, 흐름, 신호\n"
        "- 아래 4가지 중 다수가 충족되면 major_issue=true로 판단하라:\n"
        "  1. 영향 범위가 산업, 시장, 정책, 국가, 글로벌 공급망 수준이다\n"
        "  2. 실제 사건, 방향 전환, 시장 신호 같은 변화의 실체가 있다\n"
        "  3. 지금 봐야 할 시의성이 있다\n"
        "- 제목 형식, 해시태그, 영상성 표현만으로 자동 탈락시키지 마라. 내용이 주요 이슈 정의를 충족하면 통과 가능하다.\n"
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
        "- source_type이 social이면 매우 보수적으로 판단하라. 다만 내용이 정책, 시장, 기술, 기업 변화에 직접 연결되면 주요 이슈로 평가할 수 있다.\n"
        "- 해시태그 위주 제목, 릴스/쇼츠/바이럴 표현이 있어도 내용상 정책, 시장, 기술, 기업 변화가 분명하면 주요 이슈로 평가할 수 있다.\n"
        "- 반대로 제목이 멀쩡해도 실제 내용이 변화의 실체나 행동 유발성이 없으면 major_issue=false로 판단하라.\n"
        "- 기사/정책/시장 내용이 아닌 잡음성 소셜 콘텐츠는 issue_type을 signal로 두고 낮은 점수를 부여하라.\n"
        "- 입력 데이터 외 내용 생성 금지.\n"
        "- 추측 금지.\n"
        "- 기사 내용 기반으로만 작성하라.\n"
        "- 반환 키는 summary, score, reason, is_recent, issue_type, impact_scope, change_nature, major_issue 만 포함한다.\n\n"
        f"Title (keep original, do not translate): {issue.get('title', '')}\n"
        f"Content: {issue.get('content', '')}\n"
        f"URL: {issue.get('url', '')}\n"
        f"Published at: {issue.get('published_at', '')}\n"
        f"Source type: {issue.get('source_type', '')}\n"
    )

    response = llm_client.chat.completions.create(
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

    return {
        "summary": str(parsed.get("summary", "N/A")).strip() or "N/A",
        "score": _normalize_score(parsed.get("score")),
        "reason": str(parsed.get("reason", "outdated_or_uncertain")).strip()
        or "outdated_or_uncertain",
        "is_recent": bool(parsed.get("is_recent", False)),
        "issue_type": _normalize_issue_type(parsed.get("issue_type")),
        "impact_scope": _normalize_impact_scope(parsed.get("impact_scope")),
        "change_nature": _normalize_change_nature(parsed.get("change_nature")),
        "major_issue": bool(parsed.get("major_issue", False)),
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
