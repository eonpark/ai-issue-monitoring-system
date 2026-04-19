# Skills

이 문서는 FastAPI 기반 `실시간 이슈 수집 및 분석 시스템`에서 사용하는 Harness 스타일 Skill 명세다.  
각 Skill은 독립 실행 단위이며, 특정 Agent가 명확한 입력을 전달하고 명확한 출력을 받는 방식으로 설계한다.

- Collector -> Tavily Search
- Analyzer -> LLM Analyze
- Publisher -> Slack Send
- Agent 명세 문서: [agents.md](/Users/eonseon/ai-issue-monitoring-system/agents.md:1)

---

## Tavily Search

연결 Agent: [Collector](</Users/eonseon/ai-issue-monitoring-system/agents.md#1-collector>)

### Role

- 검색 질의를 받아 외부 이슈 후보를 수집한다.
- 원시 이슈 데이터를 표준 JSON 구조로 반환한다.
- Collector Agent가 사용할 수 있도록 검색 결과를 최소 필드 구조로 정규화한다.

### When to Use

- 사용자가 특정 키워드 기반 실시간 이슈 수집을 요청했을 때
- Orchestrator가 파이프라인 시작 단계에서 원시 데이터를 확보해야 할 때
- 아직 구조화된 이슈 데이터가 없고, 외부 검색 기반 수집이 필요한 경우

### Input

```json
{
  "query": "한국 실시간 주요 이슈"
}
```

### Output

```json
[
  {
    "title": "한국 실시간 주요 이슈 관련 실시간 이슈",
    "summary": "외부 검색 API 대신 기본 더미 데이터를 반환합니다.",
    "source": "mock",
    "url": "https://example.com/issues/1"
  }
]
```

### Execution Rules

- `query`는 반드시 비어 있지 않은 문자열이어야 한다.
- 반환 객체에는 최소 `title`, `summary`, `source`, `url` 필드가 있어야 한다.
- `TAVILY_API_KEY`가 있으면 `source`를 `tavily`로 설정하고, 없으면 `mock`으로 설정한다.
- 외부 API 호출이 실패하거나 API 키가 없더라도 빈 예외로 종료하지 말고 fallback 데이터를 반환해야 한다.
- 검색 결과가 없더라도 함수 계약은 유지해야 하며, 필요시 빈 배열을 반환한다.
- 반환 타입은 반드시 `list[dict]` 형태를 유지한다.
- Collector Agent 외의 다른 구성요소는 이 Skill의 내부 구현에 의존하지 말고 출력 스키마에만 의존해야 한다.

### Example Usage

Collector Agent는 다음과 같이 호출한다.

```python
from app.skills.tavily_search import search_issues

issues = search_issues(query="한국 실시간 주요 이슈")
```

또는 현재 코드 구조에서는 다음 호출과 동일하다.

```python
collector.collect(query="한국 실시간 주요 이슈")
```

---

## LLM Analyze

연결 Agent: [Analyzer](</Users/eonseon/ai-issue-monitoring-system/agents.md#2-analyzer>)

### Role

- 수집된 단일 이슈를 분석해 우선순위, 감성, 인사이트를 부여한다.
- 이슈 원본 필드를 유지한 채 분석 결과를 확장한다.
- Analyzer Agent가 여러 이슈에 대해 반복 적용할 수 있는 단일 이슈 분석 단위로 동작한다.

### When to Use

- Collector가 원시 이슈를 수집한 직후
- 이슈의 중요도나 맥락을 후속 검증/포맷팅 전에 구조화해야 할 때
- 사람 친화적 설명 또는 우선순위 기반 후처리가 필요한 경우

### Input

```json
{
  "title": "한국 실시간 주요 이슈 관련 실시간 이슈",
  "summary": "외부 검색 API 대신 기본 더미 데이터를 반환합니다.",
  "source": "mock",
  "url": "https://example.com/issues/1"
}
```

### Output

```json
{
  "title": "한국 실시간 주요 이슈 관련 실시간 이슈",
  "summary": "외부 검색 API 대신 기본 더미 데이터를 반환합니다.",
  "source": "mock",
  "url": "https://example.com/issues/1",
  "analysis_model": "gpt-4.1-mini",
  "analysis_mode": "mock",
  "sentiment": "neutral",
  "priority": "medium",
  "insight": "'한국 실시간 주요 이슈 관련 실시간 이슈' 이슈는 모니터링이 필요한 상태입니다."
}
```

### Execution Rules

- 입력 객체에는 최소 `title`이 있어야 한다.
- 입력 객체의 기존 필드는 유지해야 하며, 분석 결과는 덮어쓰기보다 확장 방식으로 추가해야 한다.
- `OPENAI_MODEL`이 없으면 기본값 `gpt-4.1-mini`를 사용한다.
- `OPENAI_API_KEY`가 있으면 `analysis_mode`를 `live`, 없으면 `mock`으로 설정한다.
- 실제 LLM 호출이 실패하더라도 파이프라인 전체를 중단시키지 말고 최소 분석 결과를 반환해야 한다.
- `sentiment`, `priority`, `insight`, `analysis_model`, `analysis_mode`는 항상 포함해야 한다.
- 출력 타입은 반드시 `dict`여야 하며, Analyzer Agent는 이 Skill을 이슈별로 독립 호출해야 한다.

### Example Usage

Analyzer Agent는 다음과 같이 호출한다.

```python
from app.skills.llm_analyze import analyze_issue

analyzed = analyze_issue(
    {
        "title": "한국 실시간 주요 이슈 관련 실시간 이슈",
        "summary": "외부 검색 API 대신 기본 더미 데이터를 반환합니다.",
        "source": "mock",
        "url": "https://example.com/issues/1",
    }
)
```

또는 현재 코드 구조에서는 다음 호출과 동일하다.

```python
analyzer.analyze(issues)
```

---

## Slack Send

연결 Agent: [Publisher](</Users/eonseon/ai-issue-monitoring-system/agents.md#5-publisher>)

### Role

- 포맷팅된 메시지를 외부 알림 채널로 전달한다.
- 현재 구현에서는 Slack Webhook 기반 발행을 담당한다.
- Publisher Agent가 최종 발행 상태를 확인할 수 있도록 전송 결과를 구조화해 반환한다.

### When to Use

- Formatter가 최종 메시지 문자열을 생성한 이후
- 외부 알림 시스템으로 결과를 전달해야 할 때
- 파이프라인 종료 시점에 발행 성공/스킵 상태를 기록해야 할 때

### Input

```json
{
  "message": "실시간 이슈 분석 결과\n1. 한국 실시간 주요 이슈 관련 실시간 이슈 | priority=medium | sentiment=neutral"
}
```

### Output

```json
{
  "status": "skipped",
  "detail": "Slack webhook not configured.",
  "message": "실시간 이슈 분석 결과\n1. 한국 실시간 주요 이슈 관련 실시간 이슈 | priority=medium | sentiment=neutral"
}
```

### Execution Rules

- 입력 메시지는 반드시 비어 있지 않은 문자열이어야 한다.
- `SLACK_WEBHOOK_URL`이 없으면 예외를 발생시키지 말고 `status=skipped`를 반환해야 한다.
- 실제 전송이 실패하더라도 파이프라인 전체를 즉시 중단시키기보다 구조화된 실패 결과를 반환하는 방향을 우선한다.
- 반환 객체에는 반드시 `status`, `detail`, `message`가 포함되어야 한다.
- Publisher Agent는 Formatter 전체 payload 중 `text`만 전달해야 하며, Skill은 메시지 문자열만 책임진다.
- 외부 채널 구현이 바뀌더라도 입력은 문자열, 출력은 상태 객체라는 계약을 유지해야 한다.

### Example Usage

Publisher Agent는 다음과 같이 호출한다.

```python
from app.skills.slack_send import send_message

result = send_message(
    "실시간 이슈 분석 결과\n1. 한국 실시간 주요 이슈 관련 실시간 이슈 | priority=medium | sentiment=neutral"
)
```

또는 현재 코드 구조에서는 다음 호출과 동일하다.

```python
publisher.publish({"text": "실시간 이슈 분석 결과\n1. ...", "issues": []})
```

---

## Agent-Skill Mapping

- `CollectorAgent.collect(query)` -> `search_issues(query)` -> [agents.md / Collector](</Users/eonseon/ai-issue-monitoring-system/agents.md#1-collector>)
- `AnalyzerAgent.analyze(issues)` -> `analyze_issue(issue)` 반복 호출 -> [agents.md / Analyzer](</Users/eonseon/ai-issue-monitoring-system/agents.md#2-analyzer>)
- `PublisherAgent.publish(payload)` -> `send_message(payload["text"])` -> [agents.md / Publisher](</Users/eonseon/ai-issue-monitoring-system/agents.md#5-publisher>)

---

## Design Principles

- 재사용성: Skill은 하나의 명확한 책임만 가져야 하며, 다른 Agent에서도 재사용 가능해야 한다.
- 독립성: Skill은 입력만으로 실행 가능해야 하며, 상위 Agent의 내부 상태에 의존하지 않아야 한다.
- 명확한 입출력: 모든 Skill은 고정된 JSON 계약을 가져야 하며, 호출자는 내부 구현이 아니라 스키마에 의존해야 한다.
- 실패 허용성: 외부 API 실패, 키 누락, 네트워크 오류가 발생해도 가능한 한 fallback 결과를 반환해야 한다.
- 확장 가능성: 현재는 stub 기반이어도 추후 실제 Tavily, OpenAI, Slack API 호출로 교체 가능해야 한다.
- 추적 가능성: 출력에는 후속 단계가 사용할 수 있는 상태 정보와 메타데이터를 포함해야 한다.
- 최소 결합: Agent는 Skill의 함수 계약만 알고 있어야 하며, Skill 내부 구현 변경이 Agent 수정으로 이어지지 않아야 한다.
