from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agents.validator import _extract_publication_date, validate_issues


def _base_issue(**overrides):
    issue = {
        "title": "Sample issue",
        "url": "https://example.com/article",
        "content": "Sample content",
        "source_type": "event",
        "summary": "샘플 요약",
        "score": 60,
        "reason": "샘플 이유",
        "is_recent": True,
        "issue_type": "event",
        "impact_scope": "regional",
        "change_nature": "concrete_change",
        "major_issue": True,
        "published_at": "2026-04-21",
        "source": "example.com",
    }
    issue.update(overrides)
    return issue


def _audit_ok(**overrides):
    audit = {
        "published_at": "2026-04-21",
        "source_verified": True,
        "content_match": True,
        "audit_reason": "matched_source_content",
    }
    audit.update(overrides)
    return audit


class ValidatorDecisionTests(unittest.TestCase):
    @patch("app.agents.validator._audit_issue")
    def test_event_threshold_boundary(self, mock_audit) -> None:
        mock_audit.return_value = _audit_ok()

        below = validate_issues([_base_issue(score=59, issue_type="event")])[0]
        at = validate_issues([_base_issue(score=60, issue_type="event")])[0]
        above = validate_issues([_base_issue(score=61, issue_type="event")])[0]

        self.assertEqual(below["status"], "NO_OK")
        self.assertEqual(at["status"], "OK")
        self.assertEqual(above["status"], "OK")

    @patch("app.agents.validator._audit_issue")
    def test_trend_threshold_boundary(self, mock_audit) -> None:
        mock_audit.return_value = _audit_ok()

        below = validate_issues([_base_issue(score=49, issue_type="trend", source_type="news")])[0]
        at = validate_issues([_base_issue(score=50, issue_type="trend", source_type="news")])[0]
        above = validate_issues([_base_issue(score=51, issue_type="trend", source_type="news")])[0]

        self.assertEqual(below["status"], "NO_OK")
        self.assertEqual(at["status"], "OK")
        self.assertEqual(above["status"], "OK")

    @patch("app.agents.validator._audit_issue")
    def test_signal_threshold_boundary(self, mock_audit) -> None:
        mock_audit.return_value = _audit_ok()

        below = validate_issues([_base_issue(score=44, issue_type="signal", source_type="social")])[0]
        at = validate_issues([_base_issue(score=45, issue_type="signal", source_type="social")])[0]
        above = validate_issues([_base_issue(score=46, issue_type="signal", source_type="social")])[0]

        self.assertEqual(below["status"], "NO_OK")
        self.assertEqual(at["status"], "OK")
        self.assertEqual(above["status"], "OK")

    @patch("app.agents.validator._audit_issue")
    def test_major_issue_false_is_rejected_even_with_high_score(self, mock_audit) -> None:
        mock_audit.return_value = _audit_ok()

        result = validate_issues([_base_issue(score=95, major_issue=False)])[0]

        self.assertEqual(result["status"], "NO_OK")
        self.assertFalse(result["validated"])
        self.assertEqual(result["validation_reason"], "주요 이슈 정의를 충족하지 않음")

    @patch("app.agents.validator._audit_issue")
    def test_limited_commentary_is_rejected(self, mock_audit) -> None:
        mock_audit.return_value = _audit_ok()

        result = validate_issues(
            [
                _base_issue(
                    score=95,
                    impact_scope="limited",
                    change_nature="commentary",
                )
            ]
        )[0]

        self.assertEqual(result["status"], "NO_OK")
        self.assertFalse(result["validated"])
        self.assertEqual(result["validation_reason"], "영향 범위가 제한적인 이슈")


class ValidatorAuditIntegrationTests(unittest.TestCase):
    @patch("app.agents.validator._audit_issue")
    def test_source_verification_failure_rejects_issue(self, mock_audit) -> None:
        mock_audit.return_value = _audit_ok(
            source_verified=False,
            content_match=False,
            audit_reason="generic_or_empty_source",
        )

        result = validate_issues([_base_issue(score=90)])[0]

        self.assertEqual(result["status"], "NO_OK")
        self.assertFalse(result["validated"])
        self.assertEqual(
            result["validation_reason"],
            "링크가 실제 본문이 아닌 일반 페이지/허브로 보이는 이슈",
        )

    @patch("app.agents.validator._audit_issue")
    def test_content_mismatch_rejects_issue(self, mock_audit) -> None:
        mock_audit.return_value = _audit_ok(
            source_verified=True,
            content_match=False,
            audit_reason="content_mismatch",
        )

        result = validate_issues([_base_issue(score=90)])[0]

        self.assertEqual(result["status"], "NO_OK")
        self.assertFalse(result["validated"])
        self.assertEqual(result["validation_reason"], "원문 내용과 요약이 충분히 일치하지 않는 이슈")


class ValidatorReasonTests(unittest.TestCase):
    @patch("app.agents.validator._audit_issue")
    def test_ok_reason_uses_issue_type_mapping(self, mock_audit) -> None:
        mock_audit.return_value = _audit_ok()

        event_result = validate_issues([_base_issue(issue_type="event", score=60)])[0]
        trend_result = validate_issues(
            [_base_issue(issue_type="trend", source_type="news", score=50)]
        )[0]
        signal_result = validate_issues(
            [_base_issue(issue_type="signal", source_type="social", score=45)]
        )[0]

        self.assertEqual(event_result["validation_reason"], "정책 방향성 이슈")
        self.assertEqual(trend_result["validation_reason"], "시장 트렌드 신호")
        self.assertEqual(signal_result["validation_reason"], "전문가 발언 기반 이슈")

    @patch("app.agents.validator._audit_issue")
    def test_audit_reason_takes_priority_over_major_issue_failure(self, mock_audit) -> None:
        mock_audit.return_value = _audit_ok(
            source_verified=False,
            content_match=False,
            audit_reason="missing_publication_date",
        )

        result = validate_issues([_base_issue(major_issue=False, score=90)])[0]

        self.assertEqual(result["status"], "NO_OK")
        self.assertEqual(result["validation_reason"], "링크에서 발행일을 확인할 수 없는 이슈")


class ValidatorPublicationDateTests(unittest.TestCase):
    def test_publication_date_does_not_use_arbitrary_body_text_date(self) -> None:
        body_text = (
            "이 기사 본문은 2019년 전쟁 상황을 설명하지만 현재 발행일 자체를 뜻하지는 않는다. "
            "추가 설명만 포함되어 있다."
        )

        extracted = _extract_publication_date(
            final_url="https://example.com/article",
            fetched_html="",
            fetched_content=body_text,
            fallback_published_at="",
        )

        self.assertEqual(extracted, "")

    def test_publication_date_can_use_structured_url_date(self) -> None:
        extracted = _extract_publication_date(
            final_url="https://example.com/2026/04/21/article",
            fetched_html="",
            fetched_content="본문",
            fallback_published_at="",
        )

        self.assertEqual(extracted, "2026-04-21")

    def test_publication_date_can_use_contextual_visible_text_date(self) -> None:
        extracted = _extract_publication_date(
            final_url="https://example.com/article",
            fetched_html="",
            fetched_content="연합뉴스 기사입력 2026.04.21 10:32 수정 2026.04.21 11:00 본문 시작",
            fallback_published_at="",
        )

        self.assertEqual(extracted, "2026-04-21")


if __name__ == "__main__":
    unittest.main()
