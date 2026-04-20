from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.analyzer import AnalyzerAgent
from app.agents.collector import collect_issues
from app.agents.formatter import FormatterAgent
from app.agents.publisher import PublisherAgent
from app.agents.validator import ValidatorAgent
from app.router import decide_next_action
from app.semantic_dedup import deduplicate_with_db
from app.state import app_state

logger = logging.getLogger(__name__)


class IssueMonitoringOrchestrator:
    def __init__(self) -> None:
        self.analyzer = AnalyzerAgent()
        self.validator = ValidatorAgent()
        self.formatter = FormatterAgent()
        self.publisher = PublisherAgent()
        self.max_steps = 10
        self.max_analyzer_candidates = 10
        self.max_retries = {
            "collector": 2,
            "analyzer": 1,
            "validator": 1,
            "formatter": 1,
            "publisher": 2,
        }

    def run_collector(self) -> list[dict[str, Any]]:
        logger.info("Collector step started")
        try:
            issues = collect_issues()
            self._last_collected_issues = list(issues)
            logger.info("Collector step finished: count=%s", len(issues))
            return issues
        except Exception as exc:  # pragma: no cover
            logger.exception("Collector step failed: %s", exc)
            return []

    def run_analyzer(self, issues: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        issues = issues or []
        logger.info("Analyzer step started: count=%s", len(issues))
        try:
            selected_issues = self._select_analyzer_candidates(issues)
            logger.info(
                "Analyzer candidate selection: before=%s after=%s",
                len(issues),
                len(selected_issues),
            )
            analyzed = self.analyzer.analyze(selected_issues)
            self._last_analyzed_issues = list(analyzed)
            logger.info("Analyzer step finished: count=%s", len(analyzed))
            return analyzed
        except Exception as exc:  # pragma: no cover
            logger.exception("Analyzer step failed: %s", exc)
            return issues

    def run_validator(self, issues: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        issues = issues or []
        logger.info("Validator step started: count=%s", len(issues))
        try:
            validated = self.validator.validate(issues)
            self._last_validated_issues = list(validated)
            for issue in validated:
                issue["validation_status"] = issue.get("status", "NO_OK")
            logger.info("Validator step finished: count=%s", len(validated))
            return validated
        except Exception as exc:  # pragma: no cover
            logger.exception("Validator step failed: %s", exc)
            return issues

    def run_semantic_dedup(self, issues: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        issues = issues or []
        logger.info("Semantic dedup step started: count=%s", len(issues))
        try:
            deduped, stats = deduplicate_with_db(issues)
            self._last_dedup_stats = stats
            logger.info("Semantic dedup step finished: count=%s", len(deduped))
            return deduped
        except Exception as exc:  # pragma: no cover
            logger.exception("Semantic dedup step failed: %s", exc)
            self._last_dedup_stats = {
                "before": len(issues),
                "after": len(issues),
                "duplicates": 0,
            }
            return issues

    def run_formatter(self, issues: list[dict[str, Any]] | None) -> str | None:
        issues = issues or []
        logger.info("Formatter step started: count=%s", len(issues))
        try:
            payload = self.formatter.format(issues)
            message = payload.get("text")
            logger.info("Formatter step finished")
            return message
        except Exception as exc:  # pragma: no cover
            logger.exception("Formatter step failed: %s", exc)
            return None

    def run_publisher(self, message: str | None) -> dict[str, Any]:
        logger.info("Publisher step started")
        if not message:
            logger.info("Publisher step skipped: empty message")
            return {"status": "skipped", "detail": "empty message", "message": ""}
        try:
            result = self.publisher.publish({"text": message})
            logger.info("Publisher step finished: status=%s", result.get("status"))
            return result
        except Exception as exc:  # pragma: no cover
            logger.exception("Publisher step failed: %s", exc)
            return {"status": "skipped", "detail": str(exc), "message": message}

    def run_pipeline(self) -> dict[str, Any]:
        logger.info("Pipeline started")
        self._last_dedup_stats = {"before": 0, "after": 0, "duplicates": 0}
        self._last_collected_issues = []
        self._last_analyzed_issues = []
        self._last_validated_issues = []
        state: dict[str, Any] = {
            "step": "start",
            "data": None,
            "message": None,
            "issues": [],
            "analyzed": False,
            "validated": False,
            "formatted": False,
            "published": False,
            "failed_action": None,
            "last_error": None,
            "retry_count": {action: 0 for action in self.max_retries},
            "max_retries": dict(self.max_retries),
        }
        actions: list[str] = []
        publish_result: dict[str, Any] | None = None

        for step_index in range(1, self.max_steps + 1):
            decision = decide_next_action(state)
            action = decision.get("action", "end")
            actions.append(action)
            logger.info("Router decision: step_index=%s action=%s", step_index, action)

            if action == "collector":
                collected = self.run_collector()
                if self._collector_succeeded(collected):
                    state["data"] = collected
                    state["issues"] = collected
                    state["step"] = "collector_done"
                    self._mark_action_success(state, "collector")
                else:
                    self._mark_action_failure(
                        state,
                        action="collector",
                        error="collector returned no issues",
                    )

            elif action == "analyzer":
                input_issues = state.get("data")
                analyzed = self.run_analyzer(input_issues)
                if self._analyzer_succeeded(input_issues, analyzed):
                    deduped = self.run_semantic_dedup(analyzed)
                    state["data"] = deduped
                    state["issues"] = deduped
                    state["step"] = "analyzer_done"
                    state["analyzed"] = True
                    self._mark_action_success(state, "analyzer")
                else:
                    self._mark_action_failure(
                        state,
                        action="analyzer",
                        error="analyzer returned no usable analysis",
                    )

            elif action == "validator":
                input_issues = state.get("data")
                validated = self.run_validator(input_issues)
                if self._validator_succeeded(input_issues, validated):
                    state["data"] = validated
                    state["issues"] = validated
                    state["step"] = "validator_done"
                    state["validated"] = True
                    self._mark_action_success(state, "validator")
                else:
                    self._mark_action_failure(
                        state,
                        action="validator",
                        error="validator returned no validation results",
                    )

            elif action == "formatter":
                formatted_message = self.run_formatter(state.get("data"))
                if self._formatter_succeeded(state.get("data"), formatted_message):
                    state["message"] = formatted_message
                    state["step"] = "formatter_done"
                    state["formatted"] = True
                    self._mark_action_success(state, "formatter")
                else:
                    self._mark_action_failure(
                        state,
                        action="formatter",
                        error="formatter failed to build message from validated issues",
                    )

            elif action == "publisher":
                publish_result = self.run_publisher(state.get("message"))
                state["publish_result"] = publish_result
                if self._publisher_succeeded(state.get("message"), publish_result):
                    state["step"] = "publisher_done"
                    state["published"] = True
                    self._mark_action_success(state, "publisher")
                else:
                    self._mark_action_failure(
                        state,
                        action="publisher",
                        error=str((publish_result or {}).get("detail", "publisher failed")),
                    )

            elif action == "end":
                logger.info("Router requested end")
                break

            else:
                logger.warning("Unknown action received: %s", action)
                state["step"] = "error"
                break
        else:
            logger.warning("Max steps reached: %s", self.max_steps)

        completed_at = datetime.now(timezone.utc).isoformat()
        app_state.set_last_run_time(completed_at)
        summary = self._build_summary(
            state=state,
            actions=actions,
            publish_result=publish_result,
            last_run_time=completed_at,
        )
        app_state.update_result(summary)
        logger.info(
            "Pipeline finished: final_step=%s total=%s sent=%s",
            summary["final_step"],
            summary["total"],
            summary["sent"],
        )
        return summary

    def run_once(self, query: str = "한국 실시간 주요 이슈") -> dict[str, Any]:
        return self.run_pipeline()

    def _build_summary(
        self,
        state: dict[str, Any],
        actions: list[str],
        publish_result: dict[str, Any] | None,
        last_run_time: str,
    ) -> dict[str, Any]:
        data = state.get("data")
        total = len(data) if isinstance(data, list) else 0
        sent = 1 if publish_result and publish_result.get("status") == "sent" else 0
        return {
            "final_step": state.get("step"),
            "actions": actions,
            "total": total,
            "processed": total,
            "sent": sent,
            "message": state.get("message"),
            "data": data,
            "publish_result": publish_result,
            "dedup": dict(self._last_dedup_stats),
            "metrics": self._build_metrics(
                collected=self._last_collected_issues,
                analyzed=self._last_analyzed_issues,
                validated=self._last_validated_issues,
                sent=sent,
            ),
            "last_error": state.get("last_error"),
            "retry_count": state.get("retry_count"),
            "last_run_time": last_run_time,
        }

    def _build_metrics(
        self,
        collected: list[dict[str, Any]],
        analyzed: list[dict[str, Any]],
        validated: list[dict[str, Any]],
        sent: int,
    ) -> dict[str, Any]:
        collector_count = len(collected)
        domestic_count = sum(1 for issue in collected if issue.get("region") == "domestic")
        global_count = sum(1 for issue in collected if issue.get("region") == "global")

        analyzer_processed = len(analyzed)
        major_issue_true_count = sum(1 for issue in analyzed if bool(issue.get("major_issue")))
        event_count = sum(1 for issue in analyzed if issue.get("issue_type") == "event")
        trend_count = sum(1 for issue in analyzed if issue.get("issue_type") == "trend")
        signal_count = sum(1 for issue in analyzed if issue.get("issue_type") == "signal")

        validator_total = len(validated)
        validator_ok_count = sum(1 for issue in validated if issue.get("status") == "OK")
        audit_pass_count = sum(
            1
            for issue in validated
            if bool(issue.get("source_verified")) and bool(issue.get("content_match"))
        )
        missing_publication_date_count = sum(
            1 for issue in validated if issue.get("audit_reason") == "missing_publication_date"
        )
        outdated_source_count = sum(
            1 for issue in validated if issue.get("audit_reason") == "outdated_source"
        )
        insufficient_content_count = sum(
            1 for issue in validated if issue.get("audit_reason") == "insufficient_fetched_content"
        )
        content_mismatch_fail_count = sum(
            1 for issue in validated if issue.get("audit_reason") == "content_mismatch"
        )
        generic_source_fail_count = sum(
            1 for issue in validated if issue.get("audit_reason") == "generic_or_empty_source"
        )
        source_verification_fail_count = max(
            0,
            validator_total
            - audit_pass_count
            - missing_publication_date_count
            - outdated_source_count
            - insufficient_content_count
            - content_mismatch_fail_count
            - generic_source_fail_count,
        )

        dedup_before = int(self._last_dedup_stats.get("before", 0))
        dedup_duplicates = int(self._last_dedup_stats.get("duplicates", 0))

        return {
            "collection": {
                "collector_count": collector_count,
                "domestic_count": domestic_count,
                "global_count": global_count,
            },
            "analysis": {
                "analyzer_processed": analyzer_processed,
                "major_issue_true_count": major_issue_true_count,
                "major_issue_rate": self._safe_ratio(major_issue_true_count, analyzer_processed),
                "event_count": event_count,
                "trend_count": trend_count,
                "signal_count": signal_count,
            },
            "audit": {
                "validator_total": validator_total,
                "validator_ok_count": validator_ok_count,
                "audit_pass_count": audit_pass_count,
                "audit_pass_rate": self._safe_ratio(audit_pass_count, validator_total),
                "missing_publication_date_count": missing_publication_date_count,
                "missing_publication_date_rate": self._safe_ratio(
                    missing_publication_date_count,
                    validator_total,
                ),
                "outdated_source_count": outdated_source_count,
                "outdated_source_rate": self._safe_ratio(
                    outdated_source_count,
                    validator_total,
                ),
                "insufficient_content_count": insufficient_content_count,
                "insufficient_content_rate": self._safe_ratio(
                    insufficient_content_count,
                    validator_total,
                ),
                "content_mismatch_fail_count": content_mismatch_fail_count,
                "content_mismatch_rate": self._safe_ratio(content_mismatch_fail_count, validator_total),
                "generic_source_fail_count": generic_source_fail_count,
                "generic_source_fail_rate": self._safe_ratio(generic_source_fail_count, validator_total),
                "source_verification_fail_count": source_verification_fail_count,
                "source_verification_fail_rate": self._safe_ratio(
                    source_verification_fail_count,
                    validator_total,
                ),
            },
            "delivery": {
                "dedup_rate": self._safe_ratio(dedup_duplicates, dedup_before),
                "validator_ok_count": validator_ok_count,
                "sent_count": sent,
            },
        }

    @staticmethod
    def _safe_ratio(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)

    def _select_analyzer_candidates(
        self,
        issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(issues) <= self.max_analyzer_candidates:
            return list(issues)

        target_per_region = self.max_analyzer_candidates // 2
        domestic = sorted(
            [issue for issue in issues if issue.get("region") == "domestic"],
            key=self._candidate_priority_key,
        )
        global_issues = sorted(
            [issue for issue in issues if issue.get("region") == "global"],
            key=self._candidate_priority_key,
        )
        other = sorted(
            [
                issue
                for issue in issues
                if issue.get("region") not in {"domestic", "global"}
            ],
            key=self._candidate_priority_key,
        )

        selected: list[dict[str, Any]] = []
        selected.extend(domestic[:target_per_region])
        selected.extend(global_issues[:target_per_region])

        selected_urls = {issue.get("url") for issue in selected if issue.get("url")}
        remainder = []
        remainder.extend(domestic[target_per_region:])
        remainder.extend(global_issues[target_per_region:])
        remainder.extend(other)
        remainder = sorted(remainder, key=self._candidate_priority_key)

        for issue in remainder:
            if len(selected) >= self.max_analyzer_candidates:
                break
            url = issue.get("url")
            if url and url in selected_urls:
                continue
            selected.append(issue)
            if url:
                selected_urls.add(url)

        return selected[: self.max_analyzer_candidates]

    @staticmethod
    def _candidate_priority_key(issue: dict[str, Any]) -> tuple[int, int, int, str]:
        source_rank = {
            "event": 0,
            "news": 1,
            "social": 2,
        }.get(str(issue.get("source_type", "")).lower(), 3)
        has_published_at = 0 if issue.get("published_at") else 1
        content_length_rank = -len((issue.get("content") or "").strip())
        title = str(issue.get("title") or "")
        return (source_rank, has_published_at, content_length_rank, title)

    def _collector_succeeded(self, issues: list[dict[str, Any]] | None) -> bool:
        return bool(issues)

    def _analyzer_succeeded(
        self,
        input_issues: list[dict[str, Any]] | None,
        analyzed: list[dict[str, Any]] | None,
    ) -> bool:
        input_items = input_issues or []
        if not input_items:
            return True
        if not analyzed:
            return False
        return any(
            item.get("score", 0) > 0 or item.get("reason") != "outdated_or_uncertain"
            for item in analyzed
        )

    def _validator_succeeded(
        self,
        input_issues: list[dict[str, Any]] | None,
        validated: list[dict[str, Any]] | None,
    ) -> bool:
        if not (input_issues or []):
            return True
        return bool(validated)

    def _formatter_succeeded(
        self,
        issues: list[dict[str, Any]] | None,
        message: str | None,
    ) -> bool:
        issue_list = issues or []
        if not issue_list:
            return True
        ok_count = sum(1 for issue in issue_list if issue.get("status") == "OK")
        if ok_count == 0:
            return True
        return bool(message) and message != "No important issues found"

    def _publisher_succeeded(
        self,
        message: str | None,
        publish_result: dict[str, Any] | None,
    ) -> bool:
        if not message:
            return True
        return (publish_result or {}).get("status") == "sent"

    def _mark_action_success(self, state: dict[str, Any], action: str) -> None:
        state["failed_action"] = None
        state["last_error"] = None
        retry_count = state.get("retry_count", {})
        if action in retry_count:
            retry_count[action] = 0

    def _mark_action_failure(self, state: dict[str, Any], action: str, error: str) -> None:
        retry_count = state.get("retry_count", {})
        retry_count[action] = retry_count.get(action, 0) + 1
        state["failed_action"] = action
        state["last_error"] = error
        state["step"] = f"{action}_failed"
        logger.warning(
            "Action failed: action=%s retry=%s/%s error=%s",
            action,
            retry_count[action],
            state.get("max_retries", {}).get(action, 0),
            error,
        )


orchestrator = IssueMonitoringOrchestrator()


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    print(orchestrator.run_pipeline())
