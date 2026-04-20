# Skills

이 문서는 FastAPI 기반 `실시간 이슈 수집 및 분석 시스템`에서 사용하는 Harness 스타일 Skill 명세다.  
각 Skill은 독립 실행 단위이며, 특정 Agent가 명확한 입력을 전달하고 명확한 출력을 받는 방식으로 설계한다.

현재 코드 기준으로 Skill은 외부 API/모델 호출과 저수준 표준화를 담당하고, Agent는 query 선택,
입력 순회, fallback, 결과 조립 같은 비즈니스 규칙을 담당한다.

- Collector -> Tavily Search
- Analyzer -> LLM Analyze
- Publisher -> Slack Send
- Agent 명세 문서: [agents.md](/Users/eonseon/ai-issue-monitoring-system/agents.md:1)

## 주요 이슈 기준

이 문서의 모든 Skill은 `agents.md`에 정의된 주요 이슈 기준을 따른다.

> 정책, 시장, 기술, 기업 활동의 변화 중에서 한국 또는 글로벌 차원의 의사결정과 모니터링이 필요한 사건, 흐름, 신호

따라서 Skill은 단순히 데이터를 가져오거나 요약하는 것이 아니라, 다음 기준에 도움이 되는 메타를 보존해야 한다.

- 영향 범위
- 변화의 실체
- 시의성

실무적으로는 아래에 가까운 항목을 우선 수집하고 해석한다.

- 정책, 규제, 법안, 제도 변화
- 시장, 투자, 실적, 공급망 변화
- 기술 방향성, 산업 구조 변화
- 기업 활동: 인수합병, 투자 유치, 파트너십, 가이던스

반대로 아래는 우선순위가 낮다.

- 단순 허브/카테고리/토픽 페이지
- 상시 소개 페이지
- 행동 유발성이 낮은 일반 정보
- 내용보다 형식이 앞서는 잡음성 소셜 콘텐츠

---

## Tavily Search

연결 Agent: [Collector](</Users/eonseon/ai-issue-monitoring-system/agents.md#1-collector>)

### Role

- 검색 질의를 사용해 외부 이슈 후보를 수집한다.
- 결과를 표준 JSON 구조로 정규화한다.
- 현재 구현에서 Tavily HTTP 호출과 검색 결과 정규화는 이 Skill이 직접 담당한다.
- 주요 이슈 판단은 하지 않고, 후속 Analyzer가 해석할 수 있도록 원시 데이터와 최소 메타만 보존한다.
- 국내(`domestic`)와 해외(`global`) query를 분리 수집한 뒤 균형 있게 합친다.
- 쿼리는 `정책 / 시장 / 기술 / 기업 활동` 변화 탐지를 우선 목표로 설계한다.
- Collector 최종 출력은 최대 20개이며, 기본적으로 국내 10개와 해외 10개를 균형 있게 유지한다.

### When to Use

- 파이프라인 시작 시 원시 이슈 후보가 필요할 때
- 주요 이슈 후보를 `domestic/global` 축과 `news/event/social` 카테고리별로 수집해야 할 때
- 아직 구조화된 이슈 데이터가 없고 외부 검색 API 기반 탐색이 필요한 경우

### Query Design Principles

- `news`는 넓은 탐색용이지만, 단순 일반 뉴스가 아니라 주요 이슈 정의에 가까운 주제어를 사용한다.
- `event`는 실제 변화 탐지용이다.
- `social`은 보조 신호 수집용이며, 최종 판단은 Analyzer가 수행한다.
- 국내와 해외는 같은 비중으로 설계해 한쪽으로 결과가 쏠리지 않게 한다.
- 쿼리는 가능한 한 아래 축을 직접 반영한다.
- 정책/규제
- 시장/투자/실적
- 기술/산업 구조
- 기업 활동/공급망
- query는 “많이 모으기”보다 “주요 이슈 정의에 가까운 후보를 모으기”에 집중한다.

### Runtime Query Config

- Collector는 아래 설정 블록을 런타임에 읽어 query 구성을 반영한다.
- 설정 로드에 실패하면 Collector 내부 기본 query 세트로 fallback 한다.

<!-- collector_query_config:start -->
```json
{
  "domestic": {
    "news": [
      "한국 주요 이슈 정책 경제 기술 산업",
      "국내 정책 변화 시장 기술 기업",
      "site:yna.co.kr OR site:hankyung.com OR site:mk.co.kr OR site:sedaily.com 한국 정책 경제 기술 기업"
    ],
    "event": [
      "국내 규제 발표 기술 정책",
      "한국 스타트업 투자 유치 인수합병",
      "국내 기업 실적 투자 공급망 발표"
    ],
    "social": [
      "site:news.ycombinator.com Korea startup policy",
      "site:reddit.com Korea economy technology policy"
    ]
  },
  "global": {
    "news": [
      "global major issues policy market technology companies",
      "world economy technology regulation supply chain",
      "site:reuters.com OR site:bloomberg.com OR site:ft.com OR site:wsj.com global policy market technology"
    ],
    "event": [
      "AI regulation announcement",
      "startup funding acquisition announcement",
      "policy change market guidance",
      "company earnings supply chain announcement"
    ],
    "social": [
      "site:twitter.com policy market technology signal",
      "site:reddit.com tech policy discussion",
      "site:news.ycombinator.com startup market regulation"
    ]
  }
}
```
<!-- collector_query_config:end -->

### Input

```json
{
  "region": "domestic",
  "query": "한국 주요 뉴스 경제 기술 정책",
  "source_type": "news",
  "time_range": "week",
  "max_results": 5
}
```

### Output

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

### Execution Rules

- `query`는 반드시 비어 있지 않은 문자열이어야 한다.
- Tavily 요청에는 최신성 옵션 `time_range`를 포함해야 한다.
- 반환 객체에는 최소 `title`, `content`, `url`, `source`, `source_type`, `region`, `published_at`가 있어야 한다.
- Collector는 주요 이슈 여부, 저품질 여부, social noise 여부를 직접 판단하지 않는다.
- 최신성, 영향 범위, 변화 성격, 주요 이슈 여부 같은 평가는 Analyzer가 담당한다.
- `url` 또는 `title`이 없는 경우만 최종 제거할 수 있다.
- social 결과는 `source_type=social`로 유지하되, 의미 판단은 Analyzer로 넘겨야 한다.
- 수집은 `domestic`와 `global`을 분리해서 수행해야 하며, 최종 결과는 한쪽으로 치우치지 않게 균형 있게 merge 해야 한다.
- 최종 merge 결과는 최대 20개여야 하며, 기본적으로 국내 10개와 해외 10개를 우선 채운다.
- query는 일반 뉴스보다 `정책 변화`, `시장 변화`, `기술 변화`, `기업 활동 변화`를 직접 겨냥해야 한다.
- `news` query에도 가능하면 `policy`, `market`, `technology`, `company`, `supply chain` 같은 변화를 나타내는 단어를 포함한다.
- `social` query는 단독 확정 소스가 아니라 조기 신호 후보로 취급한다.
- API 실패 시 예외를 삼키지 말고 구조화된 빈 배열을 반환해야 한다.

### Example Usage

Collector Agent는 다음과 같이 호출한다.

```python
from app.agents.collector import collect_issues

issues = collect_issues()
```

또는 개별 Skill 수준에서는 다음과 같은 역할을 수행한다.

```python
payload = {
    "region": "global",
    "query": "AI regulation announcement",
    "source_type": "event",
    "time_range": "week",
    "max_results": 5,
}
```

실제 Skill 함수 예시는 다음과 같다.

```python
from app.skills.tavily_search import search_issues

issues = search_issues(
    "AI regulation announcement",
    source_type="event",
    region="global",
    time_range="week",
    max_results=5,
)
```

---

## LLM Analyze

연결 Agent: [Analyzer](</Users/eonseon/ai-issue-monitoring-system/agents.md#2-analyzer>)

### Role

- 수집된 이슈 후보를 주요 이슈 정의 기준으로 해석한다.
- 한국어 요약, 점수, 판단 이유, 최근성, 이슈 유형을 생성한다.
- 현재 구현에서 OpenAI 호출과 출력 필드 정규화는 이 Skill이 직접 담당한다.
- 영향 범위, 변화의 실체, 주요 이슈 여부를 구조화된 필드로 반환한다.
- Collector가 평가하지 않은 내용적 타당성은 Analyzer가 직접 판단한다.
- 제목 형식이 아니라 내용의 실질적 변화와 영향도를 기준으로 주요 이슈 여부를 판단한다.
- 최종 링크/원문 근거 감사는 Validator가 담당한다.
- Analyzer는 Collector 결과 전체를 그대로 받지 않고, Orchestrator가 우선순위 기준으로 선별한 최대 10개 후보만 분석한다.

### When to Use

- Collector가 이슈 후보를 수집한 직후
- 수집된 결과가 `event`, `trend`, `signal` 중 어떤 유형인지 판정해야 할 때
- 후속 Validator가 사용할 구조화된 판단 결과가 필요할 때

### Candidate Selection Policy

- Analyzer 입력 후보 선택은 Agent 내부가 아니라 Orchestrator가 담당한다.
- Collector가 최대 20개를 수집한 뒤, 다음 우선순위로 최대 10개를 선택한다.
- `source_type` 우선순위: `event` -> `news` -> `social`
- `published_at`가 있는 항목을 우선한다.
- 본문(`content`)이 더 충실한 항목을 우선한다.
- 국내(`domestic`)와 해외(`global`)는 기본적으로 5개씩 균형 있게 선택한다.
- 한쪽 region 후보가 부족하면 남은 슬롯은 다른 region 후보로 채운다.

### Runtime Judgment Reference

- Analyzer는 아래 기준 블록을 런타임에 읽어 판정 필드 정의를 프롬프트에 반영한다.
- 설정 로드에 실패하면 Analyzer 내부 기본 기준으로 fallback 한다.

<!-- analyzer_field_reference:start -->
```text
이슈 유형
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
- major_issue=false: 정보성은 있으나 우선 모니터링 대상까지는 아닌 이슈
```
<!-- analyzer_field_reference:end -->

### Input

```json
{
  "title": "South Korea's tech rules could cost US, Korea $1T over 10 years",
  "content": "A study said South Korea's competition rules aimed at US tech firms could lead to large economic losses...",
  "url": "https://example.com/article",
  "source_type": "event",
  "published_at": "2026-04-20"
}
```

### Output

```json
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
  "source": "example.com"
}
```

### Execution Rules

- LLM은 입력 데이터 외 내용을 생성하면 안 된다.
- 제목은 원문 그대로 유지하고, `summary`와 `reason`은 반드시 한국어로 작성해야 한다.
- 출력은 반드시 JSON이어야 하며, 핵심 필드는 `summary`, `score`, `reason`, `is_recent`, `issue_type`, `impact_scope`, `change_nature`, `major_issue`다.
- 이슈 유형은 반드시 `event`, `trend`, `signal` 중 하나여야 한다.
- `impact_scope`는 `global`, `regional`, `limited` 중 하나여야 한다.
- `change_nature`는 `concrete_change`, `ongoing_shift`, `commentary` 중 하나여야 한다.
- `major_issue`는 주요 이슈 정의 충족 여부를 의미한다.
- `major_issue=true`는 최소한 다음 중 다수를 만족할 때만 허용한다.
- 한국 또는 글로벌 차원의 영향이 있다.
- 실제 사건, 방향 전환, 시장 신호 등 변화의 실체가 있다.
- 지금 시점에 볼 의미가 있다.
- 점수 밴드는 기본적으로 다음을 따른다.
- `event`: 70~100
- `trend`: 50~80
- `signal`: 40~70
- 최근성이 낮거나 날짜가 불명확한 경우 보수적으로 점수화해야 한다.
- 단, 의미 있는 분석/시장 신호는 오래된 문서라도 `40 이상` 가능하다.
- `source_type=social`이면 보수적으로 판단하되, 내용상 정책, 시장, 기술, 기업 변화가 분명하면 주요 이슈로 평가할 수 있다.
- 소셜/영상성 형식만으로 자동 탈락시키지 않는다. 단, 내용상 변화의 실체와 영향 범위가 없으면 `major_issue=false`로 판단해야 한다.
- 실패 시 fallback 결과를 반환해야 한다.
- fallback 기본값:
- `summary="N/A"`
- `score=0`
- `reason="outdated_or_uncertain"`
- `is_recent=false`
- `issue_type="signal"`
- `impact_scope="limited"`
- `change_nature="commentary"`
- `major_issue=false`

### Example Usage

Analyzer Agent는 다음과 같이 호출한다.

```python
from app.agents.analyzer import analyze_issues

analyzed = analyze_issues(issues)
```

실제 Skill 함수 예시는 다음과 같다.

```python
from app.skills.llm_analyze import analyze_issue

result = analyze_issue(
    issue,
    judgment_reference=judgment_reference,
)
```

---

## Slack Send

연결 Agent: [Publisher](</Users/eonseon/ai-issue-monitoring-system/agents.md#5-publisher>)

### Role

- Formatter가 만든 최종 메시지를 Slack Webhook으로 전송한다.
- 전송 성공/실패 상태를 구조화된 결과로 반환한다.
- Publisher Agent가 재시도 또는 fallback 판단을 할 수 있게 한다.

### When to Use

- Formatter가 `OK` 이슈를 Slack 보고용 메시지로 변환한 이후
- 외부 채널 발행이 필요한 마지막 단계에서
- Slack 전송 성공 여부를 상태로 남겨야 할 때

### Input

```json
{
  "message": "🔥 [AI Issue Report]\n\n1️⃣ 제목: South Korea's tech rules could cost US, Korea $1T over 10 years\n📝 요약: ...\n📊 중요도: 78\n💬 이유: ...\n🔗 관련링크: https://example.com/article"
}
```

### Output

```json
{
  "status": "sent",
  "detail": "Slack message sent successfully.",
  "message": "🔥 [AI Issue Report]\n\n1️⃣ 제목: South Korea's tech rules could cost US, Korea $1T over 10 years\n📝 요약: ...\n📊 중요도: 78\n💬 이유: ...\n🔗 관련링크: https://example.com/article"
}
```

### Execution Rules

- 입력 메시지는 반드시 문자열이어야 한다.
- `SLACK_WEBHOOK_URL`이 없으면 예외를 던지지 말고 구조화된 `skipped` 결과를 반환해야 한다.
- 실제 HTTP 전송이 실패하면 `failed` 상태와 상세 원인을 반환해야 한다.
- 반환 객체에는 항상 `status`, `detail`, `message`가 포함되어야 한다.
- Publisher Agent는 전체 payload 중 `text`만 전달하고, Skill은 메시지 전송만 책임진다.
- 성공/실패 판단은 다음 retry/fallback 로직에서 사용할 수 있도록 안정적으로 유지해야 한다.

### Example Usage

Publisher Agent는 다음과 같이 호출한다.

```python
from app.skills.slack_send import send_to_slack

result = send_to_slack(
    "🔥 [AI Issue Report]\n\n1️⃣ 제목: South Korea's tech rules could cost US, Korea $1T over 10 years\n..."
)
```

또는 현재 코드 구조에서는 다음 호출과 동일하다.

```python
publisher.publish({"text": "🔥 [AI Issue Report]\n\n1️⃣ 제목: ..."})
```

---

## Agent-Skill Mapping

- `Collector Agent -> Tavily Search Skill` -> query 그룹별 외부 검색 실행, 결과 정규화
- `Analyzer Agent -> LLM Analyze Skill` -> 단건 LLM 분석 호출, 출력 필드 정규화
- `Publisher Agent -> Slack Send Skill` -> 최종 메시지 전송

---

## Design Principles

- 재사용성: Skill은 하나의 명확한 책임만 가져야 하며, 다른 Agent에서도 재사용 가능해야 한다.
- 독립성: Skill은 입력만으로 실행 가능해야 하며, 상위 Agent의 내부 상태에 의존하지 않아야 한다.
- 명확한 입출력: 모든 Skill은 고정된 JSON 계약을 가져야 하며, 호출자는 내부 구현이 아니라 스키마에 의존해야 한다.
- 정의 우선: 주요 이슈의 의미를 먼저 고정하고, query/분석/검증은 그 정의에 맞게 정렬해야 한다.
- 보존 우선: Collector는 수집과 정규화에 집중하고, 의미 판단은 Analyzer/Validator로 넘겨야 한다.
- 실패 허용성: 외부 API 실패, 키 누락, 네트워크 오류가 발생해도 가능한 한 구조화된 fallback 결과를 반환해야 한다.
- 환각 방지: LLM Skill은 입력 외 사실을 생성하지 말고, 애매한 경우 낮은 점수와 보수적 판단을 사용해야 한다.
- 추적 가능성: 출력에는 후속 단계가 사용할 수 있는 상태 정보와 품질 메타데이터를 포함해야 한다.
- 최소 결합: Agent는 Skill의 함수 계약만 알고 있어야 하며, Skill 내부 구현 변경이 Agent 수정으로 이어지지 않아야 한다.
