# AI Issue Monitoring System

공개 검색 API와 LLM을 활용해 국내외 주요 이슈를 수집, 분석, 검증하고 Slack 및 웹 Admin 페이지로 보고하는 로컬 실행용 AI 기반 프로토타입

---

# 1. 기획 (Planning)

## 문제 정의

국내외 정책, 시장, 기술, 기업 활동은 빠르게 변한다.
하지만 주요 이슈를 사람이 직접 검색하고, 중요도를 판단하고, 팀에 공유하는 방식은 반복적이고 누락 가능성이 높다.

이 프로젝트는 다음 질문에서 출발했다.

- 지금 확인해야 할 국내외 주요 이슈는 무엇인가?
- 단순 뉴스가 아니라 의사결정에 필요한 사건, 흐름, 신호를 어떻게 구분할 것인가?
- 수집부터 보고까지 반복되는 과정을 어떻게 자동화할 것인가?

> 의사결정이란 수집된 이슈를 바탕으로 추가 모니터링, 내부 공유, 후속 조사, 리스크 확인, 전략 검토 여부를 판단하는 행동을 의미한다.

## 주요 이슈 정의

이 시스템에서 주요 이슈는 다음과 같이 정의한다.

> 정책, 시장, 기술, 기업 활동의 변화 중에서 한국 또는 글로벌 차원의 의사결정과 모니터링이 필요한 사건, 흐름, 신호

즉 단순히 조회 수가 높거나 검색에 많이 노출되는 콘텐츠가 아니라, 실제 변화와 판단 필요성이 있는 정보를 주요 이슈로 본다.

주요 이슈 판단 기준은 다음과 같다.

- 영향 범위: 산업, 시장, 정책, 국가, 글로벌 공급망 수준의 영향이 있는가
- 변화의 실체: 실제 사건, 방향 전환, 시장 신호가 존재하는가
- 시의성: 지금 확인해야 할 의미가 있는가
- 판단 필요성: 조직이나 개인의 의사결정에 참고할 가치가 있는가

이 시스템은 주요 이슈를 세 가지 유형으로 구분한다.

- `event`: 실제로 발생한 사건, 발표, 투자, 규제, 인수합병
- `trend`: 구조적이거나 지속적인 시장, 기술, 산업 흐름
- `signal`: 발언, 인터뷰, 분석, 정책 시사점, 시장 신호

반대로 다음 정보는 주요 이슈로 보지 않는다.

- 허브 페이지, 카테고리 페이지, 토픽 모음
- 일반 해설, 상시 리포트, 배경 설명
- 출처가 불명확한 소셜 잡음
- 영향 범위와 변화의 실체가 약한 정보성 콘텐츠

## 기존 방식의 한계

- 검색 결과가 많아도 실제로 중요한 이슈만 고르기 어렵다.
- 같은 이슈가 여러 출처에서 반복 수집된다.
- 기사, 보고서, 소셜 신호가 섞여 있어 중요도 판단 기준이 불명확하다.
- Slack 공유나 관리자 확인을 위해 사람이 매번 요약과 링크를 정리해야 한다.
- 단순 키워드 수집만으로는 사건, 추세, 신호를 구조적으로 분류하기 어렵다.

## 해결 방향

수집, 분석, 검증, 보고를 하나의 파이프라인으로 구성했다.

- 검색 API로 국내외 후보 이슈를 넓게 수집한다.
- LLM으로 이슈의 의미, 유형, 중요도를 구조화한다.
- 최근 DB 이슈와 비교해 중복 보고를 줄인다.
- 원문 링크를 경량 감사해 허브 페이지나 오래된 이슈를 걸러낸다.
- 최종 `OK` 이슈만 Slack과 Admin 페이지에 보고한다.

## 핵심 아이디어

이 시스템의 AI 활용 포인트는 단순 요약이 아니다.

- 이슈를 `event`, `trend`, `signal`로 분류한다.
- 영향 범위와 변화 성격을 구조화한다.
- 주요 이슈 여부와 중요도 점수를 함께 판단한다.
- embedding 기반 유사도 비교로 의미 중복을 줄인다.
- 원문 내용과 LLM 요약이 맞는지 추가 감사한다.

현재 구현은 로컬 단일 프로세스 기준 프로토타입이다. 운영 배포에 필요한 인증, 재처리 큐, 장애 알림은 추후 보완 영역으로 남겨두었다.

---

# 2. 설계 (Architecture Design)

## 전체 시스템 아키텍처

```text
[Scheduler / Admin Button]
          |
          v
   [FastAPI Server]
          |
          v
   [Orchestrator]
          |
          v
+-------------------+
| Deterministic     |
| State Router      |
+-------------------+
          |
          v
[Collector]
    |
    v
[Analyzer - LLM]
    |
    v
[Semantic Deduplication]
    |
    v
[Validator]
    |
    v
[Formatter]
    |
    v
[Publisher - Slack]
    |
    v
[SQLite DB] <------ [Admin Page]
```

Router는 자유롭게 단계를 바꾸는 LLM Router가 아니다.
현재 상태, 실패 action, retry count를 보고 다음 단계를 결정하는 deterministic state router다.

## 주요 구성 요소

### Collector

Tavily 검색 API를 사용해 국내외 이슈 후보를 수집한다.

- 국내와 해외 query group을 분리한다.
- `news`, `event`, `social` 유형의 query를 사용한다.
- URL 기준 1차 dedup을 수행한다.
- 국내 10건, 해외 10건 수준으로 균형 있게 수집한다.

### Analyzer

Analyzer는 수집된 후보를 LLM으로 해석해 “판단 가능한 이슈 데이터”로 바꾸는 단계다.
OpenAI API를 사용해 기사나 검색 결과의 의미를 요약하고, 중요도와 이슈 성격을 구조화한다.

- 한국어 요약 생성
- 중요도 점수 산정
- 이슈 유형 분류: `event`, `trend`, `signal`
- 영향 범위 분류: `global`, `regional`, `limited`
- 변화 성격 분류: `concrete_change`, `ongoing_shift`, `commentary`
- 주요 이슈 여부 판단

Analyzer는 Collector 결과 전체를 분석하지 않고 최대 10개만 선택한다. 후보 선정은 국내/해외 5:5 균형을 먼저 맞춘 뒤, event -> news -> social 순으로 우선순위를 두고, 발행일이 있는 항목과 본문 정보가 더 충실한 항목을 우선한다.

Analyzer가 만든 `score`, `major_issue`, `impact_scope`, `change_nature`는 최종 결론이 아니라 Validator가 검증에 사용하는 판단 재료다.

### Deduplication

Analyzer 이후에 중복 제거를 수행한다.

- 최근 3일 DB 이슈를 비교 대상으로 사용한다.
- 동일 URL이면 embedding 비교 전에 중복으로 제거한다.
- URL이 달라도 summary embedding의 cosine similarity가 높으면 의미 중복으로 판단한다.
- 사용 모델은 `text-embedding-3-small`이다.

### Validator

Validator는 Analyzer가 만든 판단 결과를 검증해 최종 보고 여부를 결정하는 단계다.
LLM이 산출한 점수와 분류를 그대로 믿지 않고, 규칙 기반 기준과 원문 감사 결과를 함께 확인한다.

- 이슈 유형별 threshold를 적용한다.
- `major_issue`, `impact_scope`, `change_nature`를 함께 본다.
- 링크를 fetch해 본문 텍스트를 추출한다.
- 발행일과 최신성을 확인한다.
- 원문과 요약의 일치 여부를 경량 감사한다.

최종 상태는 `OK` 또는 `NO_OK`로 결정된다.

정리하면 Analyzer는 “이 이슈가 무엇인지 해석하는 단계”이고, Validator는 “이 이슈를 실제로 보고해도 되는지 확인하는 단계”다.

### Formatter

Validator에서 `OK`로 통과한 이슈만 사람이 읽기 쉬운 Slack 메시지로 변환한다.

- 제목
- 요약
- 중요도
- 판단 이유
- 원문 링크

### Publisher

Slack webhook으로 보고 메시지를 전송한다.

Slack webhook이 설정되지 않은 경우에는 전송을 실패시키지 않고 `skipped`로 처리한다.

### DB

SQLite 로컬 DB를 사용한다.

- 이슈 결과 저장
- 실행 이력 저장
- dedup 통계 저장
- dashboard 복원용 마지막 실행 결과 저장

DB 파일은 프로젝트 루트의 `issues.db`에 생성된다.

### Scheduler

APScheduler `BackgroundScheduler`로 5분마다 파이프라인을 실행한다.

- 단일 프로세스 내부 lock으로 중복 실행을 방지한다.
- 실행 중 재호출되면 skip한다.
- multi-worker 환경에서는 별도 외부 락이 필요하다.

## 데이터 흐름

```text
검색 결과
  -> 표준 이슈 후보
  -> LLM 분석 결과
  -> 중복 제거된 분석 결과
  -> OK / NO_OK 검증 결과
  -> Slack 메시지
  -> DB 저장 및 Admin 표시
```

---

# 3. 구현 (Implementation)

## 사용 기술 스택

- Backend: FastAPI
- Scheduler: APScheduler
- Database: SQLite
- Search: Tavily API
- LLM: OpenAI API
- Embedding: `text-embedding-3-small`
- Report: Slack webhook
- Frontend: HTML, CSS, Vanilla JavaScript

## 핵심 기능 구현 내용

### 멀티소스 수집

Collector는 국내와 해외를 분리해 검색한다.
또한 `news`, `event`, `social` query를 함께 사용해 뉴스 기사뿐 아니라 정책 발표, 시장 신호, 커뮤니티 논의까지 후보로 수집한다.

수집 결과는 다음 필드 중심으로 정규화된다.

- title
- content
- url
- source
- source_type
- region
- published_at

### LLM 기반 분석

Analyzer는 수집 후보를 단순 요약하지 않고 의사결정에 필요한 필드로 구조화한다.

- 요약
- 중요도 점수
- 판단 이유
- 최근성
- 이슈 유형
- 영향 범위
- 변화 성격
- 주요 이슈 여부

이 단계에서 시스템은 단순 뉴스 목록을 “판단 가능한 이슈 데이터”로 바꾼다.

### 중복 제거

중복 제거는 두 단계로 처리한다.

1. 동일 URL 중복 제거
2. summary embedding 기반 semantic dedup

이를 통해 같은 기사가 반복 보고되는 문제와, 제목은 다르지만 의미가 같은 이슈가 중복 보고되는 문제를 줄인다.

### OK / NO_OK 판단

Validator는 Analyzer 결과를 최종 보고 가능한 이슈인지 판정한다.

현재 기준은 다음과 같다.

- `event`: score 60 이상
- `trend`: score 50 이상
- `signal`: score 45 이상
- `major_issue = true`
- 제한적 영향 범위와 단순 해설성 콘텐츠는 탈락 가능
- event는 발행일이 없거나 14일을 초과하면 탈락

추가로 원문 링크를 fetch해 본문 길이, 일반 페이지 여부, 발행일, 내용 일치 여부를 확인한다.

### Slack 연동

Formatter가 `OK` 이슈를 Slack 메시지로 만들고, Publisher가 Slack webhook으로 전송한다.

보고 메시지는 다음 정보를 포함한다.

- 제목
- 요약
- 중요도
- 판단 이유
- 관련 링크

### Admin 페이지

웹 Admin 페이지는 운영자가 파이프라인 상태와 결과를 확인하는 화면이다.

- Run Pipeline 버튼
- 실행 로그
- Scheduler 상태
- 성능 지표
- dedup 결과
- 이슈 리스트
- DB 저장 이력
- `OK / NO_OK` 필터
- 5초 자동 새로고침

### DB 저장

파이프라인 결과는 SQLite에 저장된다.

- `issues`: 최종 이슈 데이터
- `run_history`: 실행 결과, actions, publish 결과, metrics, dedup 통계

서버를 재시작해도 마지막 실행 결과와 저장 이슈를 다시 조회할 수 있다.

## 구현 시 고려한 문제와 해결 방법

### 문제 1. 수집량과 분석량 불균형

검색 후보를 많이 수집하면 비용과 시간이 증가한다.
그래서 Collector는 최대 20건, Analyzer는 우선순위가 높은 최대 10건만 처리하도록 분리했다.

우선순위는 다음 기준으로 정한다.

- `event -> news -> social`
- 발행일 존재 여부
- content 길이
- 국내/해외 5:5 균형

### 문제 2. 같은 이슈 반복 보고

같은 URL은 바로 제거한다.
URL이 다르더라도 summary embedding이 최근 DB 이슈와 유사하면 semantic duplicate로 제거한다.

### 문제 3. 오래된 이슈 또는 허브 페이지 통과

Validator에서 원문 링크를 다시 확인한다.

- HTML meta
- JSON-LD
- `<time datetime>`
- URL 날짜
- 기사 입력, 송고, 등록, Published 같은 발행 맥락 텍스트

이 정보로 발행일을 추출하고, event는 14일 기준으로 최신성을 판단한다.

### 문제 4. LLM 판단만으로는 신뢰하기 어려움

LLM 분석 결과를 그대로 보고하지 않는다.
Validator가 score, major issue 여부, 원문 감사 결과를 함께 보고 최종 `OK / NO_OK`를 결정한다.

### 문제 5. 처음 생각한 자율 에이전트 구조와 실제 코드 구조의 불일치

Router를 LLM 자유 판단 계층으로 두지 않고 deterministic state router로 정리했다.
이 방식은 현재 파이프라인처럼 단계 의존성이 강한 시스템에서 더 설명 가능하고 테스트하기 쉽다.

---

# 4. 전체 시스템 흐름 (End-to-End Flow)

## 1. 데이터 수집

Scheduler 또는 Admin 페이지의 Run Pipeline 버튼이 실행을 시작한다.
Orchestrator는 Router의 결정에 따라 Collector를 호출한다.

Collector는 Tavily API로 국내외 이슈 후보를 검색한다.

- 국내 query와 해외 query를 분리한다.
- `news`, `event`, `social` source type을 함께 사용한다.
- URL이 없거나 제목이 없는 후보는 제거한다.
- URL 기준 중복을 제거한다.
- 최대 20건 수준으로 국내외 균형을 맞춘다.

결과는 표준 issue candidate 형태로 다음 단계에 전달된다.

## 2. 분석 (LLM)

Orchestrator는 수집된 후보 중 최대 10건을 선택한다.
선택 기준은 source type, 발행일, content 충실도, 국내외 균형이다.

Analyzer는 OpenAI API를 사용해 각 후보를 분석한다.

- 핵심 요약
- 중요도 점수
- 판단 이유
- 이슈 유형
- 영향 범위
- 변화 성격
- 주요 이슈 여부

이 단계의 목적은 검색 결과를 사람이 판단 가능한 구조화 데이터로 바꾸는 것이다.

## 3. 중복 제거

Analyzer 결과는 Validator로 바로 가지 않는다.
먼저 semantic deduplication 단계를 거친다.

중복 제거는 최근 3일 DB 이슈를 기준으로 수행된다.

- 같은 URL이면 중복으로 제거한다.
- summary embedding을 생성한다.
- 최근 이슈 embedding과 cosine similarity를 비교한다.
- 유사도가 기준을 넘으면 중복으로 제거한다.

이 단계는 Slack에 같은 이슈가 반복 발행되는 문제를 줄이기 위한 장치다.

## 4. 검증 (OK / NO_OK)

Validator는 dedup 이후 남은 이슈를 최종 검증한다.

검증은 세 층으로 이루어진다.

- Analyzer 점수가 threshold를 넘는가
- 주요 이슈 정의에 맞는가
- 원문 링크가 실제 내용을 뒷받침하는가

Validator는 링크를 fetch해 본문 텍스트를 추출하고 발행일을 다시 확인한다.
event 타입은 날짜가 없거나 14일을 넘으면 `NO_OK`가 될 수 있다.

최종적으로 각 이슈는 다음 상태를 가진다.

- `OK`: Slack 보고 대상
- `NO_OK`: 저장은 가능하지만 보고 대상은 아님

## 5. 포맷팅

Formatter는 `OK` 이슈만 선택한다.
선택된 이슈를 Slack에서 읽기 쉬운 보고 메시지로 변환한다.

메시지에는 제목, 요약, 중요도, 판단 이유, 링크가 포함된다.

`OK` 이슈가 없으면 “No important issues found” 형태로 처리된다.

## 6. Slack 전송

Publisher는 Formatter가 만든 메시지를 Slack webhook으로 전송한다.

- webhook이 있으면 Slack으로 전송한다.
- webhook이 없으면 `skipped` 상태로 처리한다.
- 전송 결과는 pipeline summary에 포함된다.

## 7. DB 저장

파이프라인 실행 결과는 SQLite DB에 저장된다.

저장 대상은 두 가지다.

- 최종 이슈 목록
- 실행 이력

실행 이력에는 actions, total, processed, sent, dedup 통계, metrics, last run time이 포함된다.

Admin 페이지는 이 DB와 마지막 실행 결과를 기반으로 화면을 갱신한다.

## 8. Scheduler 반복 실행

Scheduler는 5분마다 같은 파이프라인을 반복 실행한다.

이미 실행 중이면 추가 실행을 skip한다.
이 중복 실행 방지는 현재 단일 프로세스 기준이다.

반복 실행을 통해 시스템은 주기적으로 새로운 이슈를 수집하고, 이전 이슈와 비교하며, 중복을 줄인 보고 결과를 생성한다.

---

# 5. 차별화 포인트

## 단순 크롤러가 아닌 이유

이 시스템은 검색 결과를 그대로 나열하지 않는다.

- 이슈 유형을 분류한다.
- 영향 범위와 변화 성격을 판단한다.
- 주요 이슈 여부를 구조화한다.
- 원문 링크와 최신성을 다시 확인한다.
- 중복 이슈를 제거한 뒤 보고한다.

즉 “많이 수집하는 시스템”이 아니라 “보고할 가치가 있는 이슈를 고르는 시스템”을 목표로 한다.

## AI 활용 수준

AI는 세 지점에서 사용된다.

- LLM 분석: 요약, 중요도, 유형, 영향 범위, 변화 성격 판단
- LLM 감사: 원문과 요약의 일치 여부 확인
- Embedding dedup: 의미적으로 유사한 이슈 중복 제거

AI 판단은 Validator의 규칙 기반 검증과 결합된다.
LLM 결과를 그대로 믿지 않고, score threshold와 원문 감사 결과를 함께 사용한다.

## 확장 가능성

현재 구조는 단계별 책임이 분리되어 있어 확장이 쉽다.

- 검색 API 교체 또는 추가
- DB를 SQLite에서 PostgreSQL로 변경
- Slack 외 이메일, Notion, Teams 발행 추가
- Admin 인증 추가
- 장기 저장 데이터를 활용한 성능 평가 대시보드 확장

---

# 실행 및 검증

## Conda 가상환경 생성

```bash
conda create -n ai-issue-monitoring python=3.11 -y
conda activate ai-issue-monitoring
```

## 의존성 설치

```bash
pip install -r requirements.txt
```

## 환경 변수

```env
OPENAI_API_KEY=...
TAVILY_API_KEY=...
SLACK_WEBHOOK_URL=...
```

`SLACK_WEBHOOK_URL`이 없으면 Slack 전송은 `skipped`로 처리된다.
`OPENAI_API_KEY` 또는 `TAVILY_API_KEY`가 없으면 수집과 분석 결과가 제한된다.

## 서버 실행

```bash
uvicorn app.main:app --reload
```

- API 서버: `http://127.0.0.1:8000`
- Admin 페이지: `http://127.0.0.1:8000`

## 테스트

```bash
python3 -m unittest tests.test_router tests.test_validator tests.test_db tests.test_semantic_dedup
python3 -m compileall app tests
```

현재 테스트는 Router 상태 전이, Validator 판단 규칙, DB 저장/복원, URL 및 semantic dedup 동작을 검증한다.

---

# 현재 한계

- 로컬 단일 프로세스 실행을 전제로 한다.
- `/run` API 인증은 아직 없다.
- Scheduler 중복 실행 방지는 프로세스 내부 lock 기준이다.
- 원문 감사는 `requests.get`과 정규식 기반 텍스트 추출에 의존한다.
- JavaScript 렌더링 페이지, paywall, 차단 페이지에서는 본문 감사 정확도가 낮아질 수 있다.
- 운영 배포를 위해서는 외부 락, 장애 알림, 재처리 큐, rate limit 대응이 필요하다.
