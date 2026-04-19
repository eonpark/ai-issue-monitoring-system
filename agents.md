# Agents

이 문서는 `실시간 이슈 수집 및 분석 시스템`의 에이전트 구성을 Harness 스타일로 정리한 문서다.  
실제 코드 기준 연결 대상은 다음과 같다.

- Orchestrator: `app/orchestrator.py`
- Agents: `app/agents/*.py`
- Skills: `app/skills/*.py`
- Skill 명세 문서: [skills.md](/Users/eonseon/ai-issue-monitoring-system/skills.md:1)

## 1. Collector

**Role**

- 외부 이슈 소스를 조회해 원시 이슈 데이터를 수집한다.
- 현재 구현에서는 `app/skills/tavily_search.py`의 `search_issues()`를 호출한다.
- `TAVILY_API_KEY` 존재 여부에 따라 `source`가 `tavily` 또는 `mock`으로 설정된다.
- 대응 Skill: [Tavily Search](</Users/eonseon/ai-issue-monitoring-system/skills.md#tavily-search>)

**Input**

- `query: string`
- 수집 대상 키워드 또는 검색 질의

```json
{
  "query": "한국 실시간 주요 이슈"
}
```

**Output**

- 이슈 객체 배열
- 각 객체는 최소 `title`, `summary`, `source`, `url` 필드를 가진다

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

## 2. Analyzer

**Role**

- 수집된 이슈를 LLM 기반 분석 단계로 전달한다.
- 현재 구현에서는 `app/skills/llm_analyze.py`의 `analyze_issue()`를 각 이슈별로 호출한다.
- 이슈별 감성, 우선순위, 인사이트를 부여한다.
- `OPENAI_API_KEY`, `OPENAI_MODEL` 환경 변수를 참조한다.
- 대응 Skill: [LLM Analyze](</Users/eonseon/ai-issue-monitoring-system/skills.md#llm-analyze>)

**Input**

- Collector가 반환한 이슈 배열

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

**Output**

- 분석 결과가 추가된 이슈 배열
- 기존 필드에 `analysis_model`, `analysis_mode`, `sentiment`, `priority`, `insight`가 추가된다

```json
[
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
]
```

## 3. Validator

**Role**

- 분석된 이슈 중 최소 유효성 조건을 만족하는 항목만 통과시킨다.
- 현재 구현 기준 유효 조건은 `title`과 `url` 존재 여부다.
- 통과한 이슈에는 `validated: true`가 추가된다.
- 관련 Skill: 직접 Skill을 호출하지 않고 Analyzer 출력과 Formatter 입력 사이의 검증 계층으로 동작한다.

**Input**

- Analyzer가 반환한 이슈 배열

```json
[
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
]
```

**Output**

- 유효성 검사를 통과한 이슈 배열

```json
[
  {
    "title": "한국 실시간 주요 이슈 관련 실시간 이슈",
    "summary": "외부 검색 API 대신 기본 더미 데이터를 반환합니다.",
    "source": "mock",
    "url": "https://example.com/issues/1",
    "analysis_model": "gpt-4.1-mini",
    "analysis_mode": "mock",
    "sentiment": "neutral",
    "priority": "medium",
    "insight": "'한국 실시간 주요 이슈 관련 실시간 이슈' 이슈는 모니터링이 필요한 상태입니다.",
    "validated": true
  }
]
```

## 4. Formatter

**Role**

- 검증 완료된 이슈 배열을 사람이 읽기 쉬운 메시지 형식으로 변환한다.
- 현재 구현에서는 Slack 발행 전용 텍스트 메시지를 생성한다.
- 출력은 `text`와 원본 `issues`를 함께 포함하는 payload다.
- 관련 Skill: 직접 Skill을 호출하지 않고 Publisher가 사용할 payload를 생성한다.

**Input**

- Validator 통과 후 저장된 이슈 배열
- 실제 실행 흐름에서는 `app/orchestrator.py`에서 DB 저장 후 Formatter로 전달된다

```json
[
  {
    "id": 1,
    "saved_at": "2026-04-19T00:00:00+00:00",
    "title": "한국 실시간 주요 이슈 관련 실시간 이슈",
    "summary": "외부 검색 API 대신 기본 더미 데이터를 반환합니다.",
    "source": "mock",
    "url": "https://example.com/issues/1",
    "analysis_model": "gpt-4.1-mini",
    "analysis_mode": "mock",
    "sentiment": "neutral",
    "priority": "medium",
    "insight": "'한국 실시간 주요 이슈 관련 실시간 이슈' 이슈는 모니터링이 필요한 상태입니다.",
    "validated": true
  }
]
```

**Output**

- 발행 가능한 메시지 payload 객체

```json
{
  "text": "실시간 이슈 분석 결과\n1. 한국 실시간 주요 이슈 관련 실시간 이슈 | priority=medium | sentiment=neutral",
  "issues": [
    {
      "id": 1,
      "saved_at": "2026-04-19T00:00:00+00:00",
      "title": "한국 실시간 주요 이슈 관련 실시간 이슈",
      "summary": "외부 검색 API 대신 기본 더미 데이터를 반환합니다.",
      "source": "mock",
      "url": "https://example.com/issues/1",
      "analysis_model": "gpt-4.1-mini",
      "analysis_mode": "mock",
      "sentiment": "neutral",
      "priority": "medium",
      "insight": "'한국 실시간 주요 이슈 관련 실시간 이슈' 이슈는 모니터링이 필요한 상태입니다.",
      "validated": true
    }
  ]
}
```

## 5. Publisher

**Role**

- Formatter가 만든 메시지 payload를 외부 전송 채널로 발행한다.
- 현재 구현에서는 `app/skills/slack_send.py`의 `send_message()`를 호출한다.
- `SLACK_WEBHOOK_URL` 존재 여부에 따라 실제 발행 또는 스킵 상태를 반환한다.
- 대응 Skill: [Slack Send](</Users/eonseon/ai-issue-monitoring-system/skills.md#slack-send>)

**Input**

- Formatter가 생성한 payload 객체

```json
{
  "text": "실시간 이슈 분석 결과\n1. 한국 실시간 주요 이슈 관련 실시간 이슈 | priority=medium | sentiment=neutral",
  "issues": [
    {
      "id": 1,
      "saved_at": "2026-04-19T00:00:00+00:00",
      "title": "한국 실시간 주요 이슈 관련 실시간 이슈",
      "summary": "외부 검색 API 대신 기본 더미 데이터를 반환합니다.",
      "source": "mock",
      "url": "https://example.com/issues/1",
      "analysis_model": "gpt-4.1-mini",
      "analysis_mode": "mock",
      "sentiment": "neutral",
      "priority": "medium",
      "insight": "'한국 실시간 주요 이슈 관련 실시간 이슈' 이슈는 모니터링이 필요한 상태입니다.",
      "validated": true
    }
  ]
}
```

**Output**

- 발행 결과 객체

```json
{
  "status": "skipped",
  "detail": "Slack webhook not configured.",
  "message": "실시간 이슈 분석 결과\n1. 한국 실시간 주요 이슈 관련 실시간 이슈 | priority=medium | sentiment=neutral"
}
```

## Skill 연결

각 Agent는 다음 Skill 또는 내부 로직과 연결된다.

- Collector -> `app/skills/tavily_search.py` -> [skills.md / Tavily Search](</Users/eonseon/ai-issue-monitoring-system/skills.md#tavily-search>)
- Analyzer -> `app/skills/llm_analyze.py` -> [skills.md / LLM Analyze](</Users/eonseon/ai-issue-monitoring-system/skills.md#llm-analyze>)
- Validator -> 내부 검증 로직
- Formatter -> 내부 메시지 포맷팅 로직
- Publisher -> `app/skills/slack_send.py` -> [skills.md / Slack Send](</Users/eonseon/ai-issue-monitoring-system/skills.md#slack-send>)

## 전체 실행 흐름

전체 흐름은 `app/orchestrator.py`의 `IssueMonitoringOrchestrator.run_once()` 기준으로 동작한다.

```text
1. Collector.collect(query)
2. Analyzer.analyze(collected_issues)
3. Validator.validate(analyzed_issues)
4. DB 저장
5. Formatter.format(stored_issues)
6. Publisher.publish(formatted_payload)
7. 최종 결과 반환 및 상태 갱신
```

## End-to-End Flow 예시

**Input**

```json
{
  "query": "한국 실시간 주요 이슈"
}
```

**Final Output**

```json
{
  "query": "한국 실시간 주요 이슈",
  "collected_count": 1,
  "validated_count": 1,
  "issues": [
    {
      "id": 1,
      "saved_at": "2026-04-19T00:00:00+00:00",
      "title": "한국 실시간 주요 이슈 관련 실시간 이슈",
      "summary": "외부 검색 API 대신 기본 더미 데이터를 반환합니다.",
      "source": "mock",
      "url": "https://example.com/issues/1",
      "analysis_model": "gpt-4.1-mini",
      "analysis_mode": "mock",
      "sentiment": "neutral",
      "priority": "medium",
      "insight": "'한국 실시간 주요 이슈 관련 실시간 이슈' 이슈는 모니터링이 필요한 상태입니다.",
      "validated": true
    }
  ],
  "message": "실시간 이슈 분석 결과\n1. 한국 실시간 주요 이슈 관련 실시간 이슈 | priority=medium | sentiment=neutral",
  "publish_result": {
    "status": "skipped",
    "detail": "Slack webhook not configured.",
    "message": "실시간 이슈 분석 결과\n1. 한국 실시간 주요 이슈 관련 실시간 이슈 | priority=medium | sentiment=neutral"
  }
}
```
