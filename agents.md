# Agents

이 문서는 `실시간 이슈 수집 및 분석 시스템`의 Agent 구성을 현재 코드 기준으로 정리한 문서다.

- Orchestrator: `app/orchestrator.py`
- Router: `app/router.py`
- Agents: `app/agents/*.py`
- Skills: `app/skills/*.py`
- Skill 명세 문서: [skills.md](/Users/eonseon/ai-issue-monitoring-system/skills.md:1)

## Router 역할

현재 Router는 LLM 자유 판단 레이어가 아니라, 파이프라인 순서 보장과 실패 복구를 담당하는
`deterministic state router`로 동작한다.

- 현재 상태(`step`, `failed_action`, `retry_count`)를 바탕으로 다음 action을 결정한다.
- 실행 순서는 고정 상태 전이 규칙을 따른다.
- 재시도 한도를 넘기면 단계별 fallback 규칙에 따라 이전 단계로 복귀하거나 종료한다.
- 의미 판단은 Router가 아니라 Analyzer와 Validator의 LLM/규칙 로직이 담당한다.

## 주요 이슈 정의

이 시스템에서 `주요 이슈`는 다음과 같이 정의한다.

> 정책, 시장, 기술, 기업 활동의 변화 중에서 한국 또는 글로벌 차원의 의사결정과 모니터링이 필요한 사건, 흐름, 신호

주요 이슈 판단 기준은 다음 4가지다.

- 영향 범위: 산업, 시장, 정책, 국가, 글로벌 공급망 수준의 영향이 있는가
- 변화의 실체: 실제 사건, 방향 전환, 시장 신호가 존재하는가
- 시의성: 지금 봐야 할 의미가 있는가

다음은 주요 이슈로 보지 않는다.

- 허브 페이지, 카테고리 페이지, 토픽 모음
- 일반 해설, 상시 리포트, 배경 설명
- 출처 불명확한 소셜 잡음
- 영향 범위와 변화의 실체가 약한 정보성 콘텐츠

## 이슈 유형 정의

Analyzer와 Validator는 주요 이슈를 아래 3개 유형으로 구분한다.

- `event`: 실제로 발생한 사건
- `trend`: 구조적이거나 지속적인 흐름
- `signal`: 발언, 인터뷰, 분석, 정책 시사점, 시장 신호

## 1. Collector

**Role**

- 외부 검색 API를 사용해 이슈 후보를 최대한 넓게 수집한다.
- 현재 구현은 Tavily REST API를 호출한다.
- Agent는 query 그룹 로딩, region balance, dedup, 최소 정규화를 담당한다.
- 실제 외부 검색 호출과 검색 결과 표준화는 `app/skills/tavily_search.py`가 담당한다.
- `skills.md`의 Collector query 설정 블록을 읽어 `domestic/global`과 `news/event/social` 구성을 반영한다.
- 여러 query 카테고리(`news`, `event`, `social`)를 사용한다.
- 국내와 해외 결과를 분리 수집한 뒤 균형 있게 merge 한다.
- 최종 수집 결과는 최대 20개이며, 기본적으로 국내 10개와 해외 10개를 균형 있게 맞춘다.
- Collector는 판단보다 수집과 정규화에 집중한다.
- 주요 이슈 여부, 영향 범위, 변화 성격 같은 해석은 Analyzer와 Validator가 담당한다.
- 대응 Skill: [Tavily Search](</Users/eonseon/ai-issue-monitoring-system/skills.md#tavily-search>)

**Input**

- 내부 고정 query 세트 사용
- 실행 시 별도 입력은 없고 orchestrator가 Collector를 호출한다

```json
{
  "queries": [
    {"region": "domestic", "query": "한국 주요 뉴스 경제 기술 정책", "source_type": "news"},
    {"region": "domestic", "query": "국내 AI 규제 발표", "source_type": "event"},
    {"region": "global", "query": "AI regulation announcement", "source_type": "event"},
    {"region": "global", "query": "site:reddit.com tech discussion", "source_type": "social"}
  ]
}
```

**Output**

- 원시 이슈 후보 배열
- 각 항목은 제목, 본문, 링크, 출처, source_type, region, published_at 중심으로 정규화된다

```json
[
  {
    "title": "South Korea's tech rules could cost US, Korea $1T over 10 years",
    "content": "A study said South Korea's competition rules aimed at US tech firms could lead to large economic losses...",
    "url": "https://example.com/article",
    "source": "example.com",
    "source_type": "event",
    "region": "global",
    "published_at": "2026-04-20"
  }
]
```

## 2. Analyzer

**Role**

- 수집된 이슈를 LLM으로 요약하고 중요도를 평가한다.
- Agent는 입력 순회, judgment reference 로딩, fallback 처리, 결과 조립을 담당한다.
- 실제 LLM 호출과 출력 필드 정규화는 `app/skills/llm_analyze.py`가 담당한다.
- 주요 이슈 정의를 기준으로 `event`, `trend`, `signal`을 판정한다.
- Collector가 넘긴 원시 데이터만 바탕으로 주요 이슈 여부를 해석한다.
- 영향 범위, 변화의 실체, 시의성을 구조적으로 판단한다.
- Collector 결과 전체를 그대로 분석하지 않고, Orchestrator가 우선순위 기준으로 선별한 최대 10개 후보만 분석한다.
- 대응 Skill: [LLM Analyze](</Users/eonseon/ai-issue-monitoring-system/skills.md#llm-analyze>)

**Input**

- Collector가 반환한 이슈 배열

```json
[
  {
    "title": "South Korea's tech rules could cost US, Korea $1T over 10 years",
    "content": "A study said South Korea's competition rules aimed at US tech firms could lead to large economic losses...",
    "url": "https://example.com/article",
    "source": "example.com",
    "source_type": "event",
    "region": "global",
    "published_at": "2026-04-20"
  }
]
```

**Output**

- 제목 원문은 유지하고, 요약과 판단 이유는 한국어로 생성한다
- 중요도 점수와 최근성, 이슈 유형을 함께 반환한다

```json
[
  {
    "title": "South Korea's tech rules could cost US, Korea $1T over 10 years",
    "url": "https://example.com/article",
    "source_type": "event",
    "summary": "한국과 미국의 기술 기업 규제 정책이 양국 경제에 큰 손실을 유발할 수 있다는 분석이다.\n기술 산업과 정책 환경에 실질적 영향을 줄 수 있는 사건으로 해석된다.",
    "score": 78,
    "reason": "한미 양국의 기술 산업과 정책 환경에 영향을 줄 수 있어 경제적 파급력이 크다. 단순 의견이 아니라 규제 방향성과 연결된 사건성이 있다.",
    "is_recent": true,
    "issue_type": "event",
    "impact_scope": "regional",
    "change_nature": "concrete_change",
    "major_issue": true,
    "published_at": "2026-04-20",
    "source": "example.com",
    "region": "global"
  }
]
```

## 3. Validator

**Role**

- Analyzer 결과를 최종 보고 대상인지 여부로 판정한다.
- 현재는 `issue_type`, `score`, `major_issue`, `impact_scope`, `change_nature`를 함께 보고 `OK / NO_OK`를 결정한다.
- 추가로 링크를 간단히 fetch 하거나 수집된 content와 비교해, 요약이 원문 근거를 실제로 뒷받침하는지 가볍게 감사한다.
- 관련 Skill: 직접 Skill을 호출하지 않고 Analyzer 출력과 Formatter 입력 사이의 판단 계층으로 동작한다.

**Input**

- Analyzer가 반환한 이슈 배열

```json
[
  {
    "title": "South Korea's tech rules could cost US, Korea $1T over 10 years",
    "url": "https://example.com/article",
    "source_type": "event",
    "summary": "한국과 미국의 기술 기업 규제 정책이 양국 경제에 큰 손실을 유발할 수 있다는 분석이다.\n기술 산업과 정책 환경에 실질적 영향을 줄 수 있는 사건으로 해석된다.",
    "score": 78,
    "reason": "한미 양국의 기술 산업과 정책 환경에 영향을 줄 수 있어 경제적 파급력이 크다. 단순 의견이 아니라 규제 방향성과 연결된 사건성이 있다.",
    "is_recent": true,
    "issue_type": "event",
    "impact_scope": "regional",
    "change_nature": "concrete_change",
    "major_issue": true
  }
]
```

**Output**

- 최종 보고 여부와 판정 이유가 추가된 이슈 배열

```json
[
  {
    "title": "South Korea's tech rules could cost US, Korea $1T over 10 years",
    "url": "https://example.com/article",
    "source_type": "event",
    "summary": "한국과 미국의 기술 기업 규제 정책이 양국 경제에 큰 손실을 유발할 수 있다는 분석이다.\n기술 산업과 정책 환경에 실질적 영향을 줄 수 있는 사건으로 해석된다.",
    "score": 78,
    "reason": "한미 양국의 기술 산업과 정책 환경에 영향을 줄 수 있어 경제적 파급력이 크다. 단순 의견이 아니라 규제 방향성과 연결된 사건성이 있다.",
    "is_recent": true,
    "issue_type": "event",
    "status": "OK",
    "validated": true,
    "validation_reason": "정책 방향성 이슈",
    "validation_status": "OK"
  }
]
```

## 4. Formatter

**Role**

- Validator 결과 중 `OK`인 항목을 Slack 보고 메시지로 변환한다.
- 현재는 사람이 읽기 쉬운 텍스트 메시지를 생성하고 관련 링크를 포함한다.
- 관련 Skill: 직접 Skill을 호출하지 않고 Publisher가 사용할 메시지를 생성한다.

**Input**

- Validator 결과 배열

```json
[
  {
    "title": "South Korea's tech rules could cost US, Korea $1T over 10 years",
    "url": "https://example.com/article",
    "summary": "한국과 미국의 기술 기업 규제 정책이 양국 경제에 큰 손실을 유발할 수 있다는 분석이다.\n기술 산업과 정책 환경에 실질적 영향을 줄 수 있는 사건으로 해석된다.",
    "score": 78,
    "reason": "한미 양국의 기술 산업과 정책 환경에 영향을 줄 수 있어 경제적 파급력이 크다. 단순 의견이 아니라 규제 방향성과 연결된 사건성이 있다.",
    "status": "OK",
    "validation_reason": "정책 방향성 이슈"
  }
]
```

**Output**

- Slack에 바로 보낼 수 있는 메시지 문자열

```json
{
  "text": "🔥 [AI Issue Report]\n\n1️⃣ 제목: South Korea's tech rules could cost US, Korea $1T over 10 years\n📝 요약: 한국과 미국의 기술 기업 규제 정책이 양국 경제에 큰 손실을 유발할 수 있다는 분석이다.\n📊 중요도: 78\n💬 이유: 한미 양국의 기술 산업과 정책 환경에 영향을 줄 수 있어 경제적 파급력이 크다. 단순 의견이 아니라 규제 방향성과 연결된 사건성이 있다.\n🔗 관련링크: https://example.com/article",
  "issues": [
    {
      "title": "South Korea's tech rules could cost US, Korea $1T over 10 years",
      "status": "OK"
    }
  ]
}
```

## 5. Publisher

**Role**

- Formatter가 만든 메시지를 외부 채널로 전송한다.
- 현재 구현 채널은 Slack webhook이다.
- 대응 Skill: [Slack Send](</Users/eonseon/ai-issue-monitoring-system/skills.md#slack-send>)

**Input**

- Formatter가 생성한 메시지 문자열

```json
{
  "text": "🔥 [AI Issue Report]\n\n1️⃣ 제목: South Korea's tech rules could cost US, Korea $1T over 10 years\n📝 요약: ...\n📊 중요도: 78\n💬 이유: ...\n🔗 관련링크: https://example.com/article"
}
```

**Output**

- 전송 결과 객체

```json
{
  "status": "sent",
  "detail": "Slack message sent successfully.",
  "message": "🔥 [AI Issue Report]\n\n1️⃣ 제목: South Korea's tech rules could cost US, Korea $1T over 10 years\n📝 요약: ...\n📊 중요도: 78\n💬 이유: ...\n🔗 관련링크: https://example.com/article"
}
```

## Skill 연결

- Collector Agent -> `app/skills/tavily_search.py` -> [skills.md / Tavily Search](</Users/eonseon/ai-issue-monitoring-system/skills.md#tavily-search>)
- Analyzer Agent -> `app/skills/llm_analyze.py` -> [skills.md / LLM Analyze](</Users/eonseon/ai-issue-monitoring-system/skills.md#llm-analyze>)
- Validator -> 내부 판단 로직
- Formatter -> 내부 메시지 포맷팅 로직
- Publisher Agent -> `app/skills/slack_send.py` -> [skills.md / Slack Send](</Users/eonseon/ai-issue-monitoring-system/skills.md#slack-send>)

## 주요 이슈 판정 규칙

현재 Validator의 판정 기준은 다음과 같다.

- `event`: `score >= 60` -> `OK`
- `trend`: `score >= 50` -> `OK`
- `signal`: `score >= 45` -> `OK`

추가로 아래 기준을 함께 본다.

- `major_issue = true` 여야 한다
- `impact_scope`가 `limited`이고 `change_nature`가 `commentary`이면 탈락할 수 있다
- `change_nature = commentary`이고 영향 범위가 좁으면 탈락할 수 있다

## 전체 실행 흐름

전체 흐름은 `app/orchestrator.py`의 `IssueMonitoringOrchestrator.run_pipeline()` 기준으로 동작한다.

```text
1. Router.decide_next_action(state)
2. Collector.collect_issues()
3. Orchestrator.select_analyzer_candidates(collected_issues)
4. Analyzer.analyze_issues(selected_issues)
5. Validator.validate_issues(analyzed_issues)
6. Formatter.format_issues(validated_issues)
7. Publisher.publish(message)
8. 결과 저장 및 상태 갱신
```

Router는 위 순서를 임의로 바꾸지 않는다. 현재 구현은 상태머신 기반으로 다음 단계만 결정한다.

## 수집/분석 수량 정책

- Collector는 region 균형을 맞춰 최대 20개까지 반환한다.
- Analyzer는 이 20개 전체를 그대로 분석하지 않고, 우선순위가 높은 최대 10개만 분석한다.
- 우선순위 기준은 다음과 같다.
- `source_type`: `event` -> `news` -> `social`
- `published_at` 존재 여부
- `content` 충실도
- `region` 균형: 국내 5개, 해외 5개 우선
- 이 정책의 목적은 5분 주기 실행 환경에서 검색 비용과 중복 후보를 줄이면서, 분석 대상 선정 기준을 명확하게 유지하는 것이다.

## Failure Fallback

Router와 Orchestrator는 API 실패 또는 비정상 결과에 대해 재시도와 이전 단계 복귀를 지원한다.

- `collector` 실패 -> 최대 2회 재시도 후 `end`
- `analyzer` 실패 -> 1회 재시도 후 `collector`로 복귀
- `validator` 실패 -> 1회 재시도 후 `analyzer`로 복귀
- `formatter` 실패 -> 1회 재시도 후 `validator`로 복귀
- `publisher` 실패 -> 최대 2회 재시도 후 `formatter`로 복귀

## End-to-End Flow 예시

**Final Output**

```json
{
  "final_step": "publisher_done",
  "actions": ["collector", "analyzer", "validator", "formatter", "publisher", "end"],
  "total": 3,
  "processed": 3,
  "sent": 1,
  "message": "🔥 [AI Issue Report]\n\n1️⃣ 제목: South Korea's tech rules could cost US, Korea $1T over 10 years\n📝 요약: ...\n📊 중요도: 78\n💬 이유: ...\n🔗 관련링크: https://example.com/article",
  "data": [
    {
      "title": "South Korea's tech rules could cost US, Korea $1T over 10 years",
      "issue_type": "event",
      "status": "OK",
      "validation_reason": "정책 방향성 이슈"
    },
    {
      "title": "The Fracturing of the Global Economy - Capital Economics",
      "issue_type": "trend",
      "status": "OK",
      "validation_reason": "시장 트렌드 신호"
    },
    {
      "title": "Some noisy social post",
      "issue_type": "signal",
      "status": "NO_OK",
      "validation_reason": "저품질 또는 무관한 소셜/콘텐츠 신호"
    }
  ],
  "publish_result": {
    "status": "sent",
    "detail": "Slack message sent successfully."
  }
}
```
