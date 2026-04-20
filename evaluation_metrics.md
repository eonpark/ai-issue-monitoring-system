# Evaluation Metrics

이 문서는 `실시간 이슈 수집 및 분석 시스템`의 성능 평가 지표를 현재 구조에 맞게 단순하고 직관적으로 정의한다.

목표는 세 가지다.

- 좋은 이슈를 충분히 모으는가
- 근거가 약한 이슈를 잘 걸러내는가
- 최종적으로 Slack에 보낼 만한 결과가 안정적으로 나오는가

정답셋 없이도 운영 중 지속적으로 볼 수 있는 지표만 포함한다.

---

## 1. 핵심 지표

가장 먼저 보는 지표는 아래 8개다.

### 1. 수집 건수

- 의미: Collector가 이번 실행에서 최종 후보를 몇 건 확보했는가
- 계산:

```text
collector_count = collector 최종 결과 개수
```

### 2. 국내/해외 균형

- 의미: 결과가 한쪽으로 치우치지 않았는가
- 계산:

```text
domestic_count
global_count
domestic_ratio = domestic_count / (domestic_count + global_count)
```

- 해석:
- `domestic_ratio`가 너무 낮으면 해외 편향
- 너무 높으면 국내 편향

### 3. 주요 이슈 판정 비율

- 의미: Analyzer가 주요 이슈 후보로 본 비율
- 계산:

```text
major_issue_rate = analyzer_major_issue_true / analyzer_processed
```

- 해석:
- 너무 높으면 Analyzer가 느슨함
- 너무 낮으면 Analyzer가 과하게 보수적임

### 4. 근거 검증 통과율

- 의미: Validator의 원문 감사 규칙을 통과한 비율
- 계산:

```text
audit_pass_rate = validator_audit_pass / validator_total
```

- 해석:
- 낮을수록 허브/홈/내용 불일치 링크가 많음

### 5. 내용 불일치 실패율

- 의미: 요약/제목과 원문 내용이 충분히 맞지 않아 탈락한 비율
- 계산:

```text
content_mismatch_rate = validator_content_mismatch_fail / validator_total
```

### 6. 일반 링크 실패율

- 의미: 메인페이지, 허브, 근거 부족 링크로 탈락한 비율
- 계산:

```text
generic_source_fail_rate = validator_generic_source_fail / validator_total
```

### 7. 중복 제거율

- 의미: Semantic dedup이 실제로 얼마나 줄였는가
- 계산:

```text
dedup_rate = dedup_duplicates / dedup_before
```

### 8. 최종 발행율

- 의미: 최종적으로 Slack까지 간 이슈 비율
- 계산:

```text
publish_rate = sent_count / validator_ok_count
```

- 해석:
- `validator_ok_count > 0`인데 `publish_rate`가 낮으면 발행 단계 문제

---

## 2. 에이전트별 평가 기준

## Collector

Collector는 “얼마나 많이”보다 “균형 있게 후보를 확보했는가”를 본다.

- `collector_count`
- `domestic_count`
- `global_count`
- `news_count`
- `event_count`
- `social_count`

Collector가 잘 동작한다고 보는 기준:

- 결과가 0건이 아님
- 국내/해외가 한쪽으로 심하게 치우치지 않음
- `social`만 과도하게 많지 않음

## Analyzer

Analyzer는 주요 이슈 정의에 맞게 구조화하는지를 본다.

- `analyzer_processed`
- `major_issue_true_count`
- `major_issue_rate`
- `event_count`
- `trend_count`
- `signal_count`
- `global_scope_count`
- `regional_scope_count`
- `limited_scope_count`

Analyzer가 잘 동작한다고 보는 기준:

- `major_issue=true`가 너무 많지 않음
- `signal`만 과도하게 많지 않음
- `limited + commentary` 비율이 너무 높지 않음

## Validator

Validator는 현재 가장 중요한 성능 지점이다.

- `validator_total`
- `validator_ok_count`
- `validator_no_ok_count`
- `validator_audit_pass_count`
- `validator_source_verified_fail_count`
- `validator_content_mismatch_fail_count`
- `validator_generic_source_fail_count`

Validator가 잘 동작한다고 보는 기준:

- 근거 부족 링크를 일정 비율 이상 걸러냄
- 내용 불일치 실패가 실제로 감지됨
- OK 결과가 과도하게 많지 않음

## Semantic Dedup

- `dedup_before`
- `dedup_after`
- `dedup_duplicates`
- `dedup_rate`

Dedup이 잘 동작한다고 보는 기준:

- 중복이 일정 수준 줄어듦
- 과하게 많이 제거되지는 않음

## Publisher

- `publish_attempted`
- `sent_count`
- `publish_status`
- `empty_publish`

Publisher가 잘 동작한다고 보는 기준:

- `publish_status=sent`
- `empty_publish` 비율이 지나치게 높지 않음

---

## 3. 최소 저장 필드 설계

`run_history`에는 아래 필드만 추가 저장하면 충분하다.

```text
collector_count
collector_domestic_count
collector_global_count
collector_news_count
collector_event_count
collector_social_count

analyzer_processed
analyzer_major_issue_true_count
analyzer_event_count
analyzer_trend_count
analyzer_signal_count
analyzer_global_scope_count
analyzer_regional_scope_count
analyzer_limited_scope_count

validator_total
validator_ok_count
validator_no_ok_count
validator_audit_pass_count
validator_source_verified_fail_count
validator_content_mismatch_fail_count
validator_generic_source_fail_count

dedup_before
dedup_after
dedup_duplicates

publish_attempted
empty_publish
```

이 정도면 에이전트별 핵심 성능을 모두 볼 수 있다.

---

## 4. 프론트 표시 설계

프론트에는 너무 많은 수치를 올리지 않고 아래 4개 카드만 두는 것이 좋다.

### Card 1. Collection Balance

- `collector_count`
- `domestic_count`
- `global_count`

표시 예:

```text
Collected: 18
Domestic: 9
Global: 9
```

### Card 2. Major Issue Analysis

- `major_issue_rate`
- `event / trend / signal`

표시 예:

```text
Major Issue Rate: 55%
Event 4 / Trend 3 / Signal 3
```

### Card 3. Source Audit

- `audit_pass_rate`
- `missing_publication_date_rate`
- `outdated_source_rate`
- `insufficient_content_rate`
- `generic_source_fail_rate`
- `content_mismatch_rate`
- `source_verification_fail_rate`

표시 예:

```text
통과: 40%
날짜 없음: 10%
오래됨: 10%
본문 부족: 20%
일반 페이지: 10%
내용 불일치: 5%
링크 검증 실패: 5%
```

### Card 4. Dedup & Publish

- `dedup_rate`
- `validator_ok_count`

표시 예:

```text
중복 제거: 25%
최종 OK: 6
```

---

## 5. 운영 해석 가이드

### 케이스 1. 수집은 많은데 OK가 거의 없음

- Collector query가 너무 넓음
- Analyzer가 너무 보수적이거나
- Validator 감사가 너무 엄격할 수 있음

우선 보는 지표:

- `major_issue_rate`
- `audit_pass_rate`

### 케이스 2. Slack에 이상한 이슈가 자주 감

- Validator 감사가 약함
- `generic_source_fail_rate`, `source_verification_fail_rate`가 낮게 잡힐 수 있음

우선 보는 지표:

- `validator_ok_count`
- `validator_source_verification_fail_count`
- `validator_content_mismatch_fail_count`
- `validator_generic_source_fail_count`

### 케이스 3. 같은 이슈가 반복됨

- Dedup이 약함

우선 보는 지표:

- `dedup_duplicates`
- `dedup_rate`

### 케이스 4. 해외 기사만 많음

- Collector 균형 문제

우선 보는 지표:

- `collector_domestic_count`
- `collector_global_count`

---

## 6. 최종 권장안

처음부터 복잡한 평가 체계를 만들지 말고, 아래 6개만 먼저 저장하고 프론트에 보여주는 것이 좋다.

- `collector_count`
- `domestic_count`
- `global_count`
- `major_issue_rate`
- `audit_pass_rate`
- `dedup_rate`
- `validator_ok_count`
- `sent_count`

이 8개면 현재 시스템의 품질을 직관적으로 볼 수 있다.

한 줄 기준:

- 많이 모였는가
- 균형 잡혔는가
- 주요 이슈로 잘 해석했는가
- 근거가 맞는가
- 중복이 줄었는가
- 최종 발행이 됐는가
