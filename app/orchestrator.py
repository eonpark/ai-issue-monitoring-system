from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.agents.analyzer import AnalyzerAgent
from app.agents.collector import CollectorAgent
from app.agents.formatter import FormatterAgent
from app.agents.publisher import PublisherAgent
from app.agents.validator import ValidatorAgent
from app.db import db
from app.state import app_state

logger = logging.getLogger(__name__)


class IssueMonitoringOrchestrator:
    def __init__(self) -> None:
        self.collector = CollectorAgent()
        self.analyzer = AnalyzerAgent()
        self.validator = ValidatorAgent()
        self.formatter = FormatterAgent()
        self.publisher = PublisherAgent()

    def run_collector(self, query: str) -> list[dict[str, Any]]:
        logger.info("Collector started")
        try:
            issues = self.collector.collect(query=query)
            normalized = [self._normalize_issue(issue) for issue in issues]
            logger.info("Collector finished: collected=%s", len(normalized))
            return normalized
        except Exception as exc:  # pragma: no cover
            logger.exception("Collector failed: %s", exc)
            fallback = [self._build_fallback_issue(query=query, stage="collector")]
            logger.info("Collector fallback applied: collected=%s", len(fallback))
            return fallback

    def run_analyzer(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        logger.info("Analyzer started: input=%s", len(issues))
        if not issues:
            logger.info("Analyzer skipped: no issues")
            return []
        try:
            analyzed = self.analyzer.analyze(issues)
            logger.info("Analyzer finished: analyzed=%s", len(analyzed))
            return analyzed
        except Exception as exc:  # pragma: no cover
            logger.exception("Analyzer failed: %s", exc)
            fallback = [self._fallback_analyzed_issue(issue) for issue in issues]
            logger.info("Analyzer fallback applied: analyzed=%s", len(fallback))
            return fallback

    def run_validator(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        logger.info("Validator started: input=%s", len(issues))
        if not issues:
            logger.info("Validator skipped: no issues")
            return []
        try:
            validated = self.validator.validate(issues)
            ok_urls = {issue.get("url") for issue in validated}
            marked: list[dict[str, Any]] = []
            for issue in issues:
                enriched = dict(issue)
                status = "OK" if issue.get("url") in ok_urls else "NO_OK"
                enriched["validation_status"] = status
                enriched["validated"] = status == "OK"
                marked.append(enriched)
            logger.info(
                "Validator finished: total=%s ok=%s no_ok=%s",
                len(marked),
                len([item for item in marked if item["validated"]]),
                len([item for item in marked if not item["validated"]]),
            )
            return marked
        except Exception as exc:  # pragma: no cover
            logger.exception("Validator failed: %s", exc)
            fallback = [self._fallback_validated_issue(issue) for issue in issues]
            logger.info("Validator fallback applied: validated=%s", len(fallback))
            return fallback

    def run_formatter(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        logger.info("Formatter started: input=%s", len(issues))
        ok_issues = [issue for issue in issues if issue.get("validated")]
        if not ok_issues:
            logger.info("Formatter skipped: no validated issues")
            return []
        try:
            formatted = self.formatter.format(ok_issues)
            payload = [
                {
                    "text": formatted.get("text", "실시간 이슈 분석 결과"),
                    "issues": formatted.get("issues", ok_issues),
                }
            ]
            logger.info("Formatter finished: payloads=%s", len(payload))
            return payload
        except Exception as exc:  # pragma: no cover
            logger.exception("Formatter failed: %s", exc)
            fallback_text = self._build_fallback_message(ok_issues)
            payload = [{"text": fallback_text, "issues": ok_issues}]
            logger.info("Formatter fallback applied: payloads=%s", len(payload))
            return payload

    def run_publisher(self, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        logger.info("Publisher started: input=%s", len(payloads))
        if not payloads:
            logger.info("Publisher skipped: no payloads")
            return []
        try:
            results = [self.publisher.publish(payload) for payload in payloads]
            logger.info("Publisher finished: results=%s", len(results))
            return results
        except Exception as exc:  # pragma: no cover
            logger.exception("Publisher failed: %s", exc)
            fallback = [
                {
                    "status": "skipped",
                    "detail": f"Publisher fallback applied: {exc}",
                    "message": payload.get("text", ""),
                }
                for payload in payloads
            ]
            logger.info("Publisher fallback applied: results=%s", len(fallback))
            return fallback

    def run_pipeline(self, query: str = "한국 실시간 주요 이슈") -> dict[str, Any]:
        logger.info("Pipeline started: query=%s", query)
        last_run_time = app_state.get_last_run_time()

        collected = self.run_collector(query=query)
        total = len(collected)

        deduped = self._deduplicate_issues(collected)
        logger.info("Dedup finished: before=%s after=%s", len(collected), len(deduped))

        filtered = self._filter_new_issues(deduped, last_run_time=last_run_time)
        logger.info(
            "Filter finished: last_run_time=%s before=%s after=%s",
            last_run_time,
            len(deduped),
            len(filtered),
        )

        analyzed = self.run_analyzer(filtered)
        validated = self.run_validator(analyzed)
        stored = self._store_issues(validated)
        formatted_payloads = self.run_formatter(stored)
        publish_results = self.run_publisher(formatted_payloads)

        sent = sum(1 for result in publish_results if result.get("status") == "sent")
        processed = len([issue for issue in stored if issue.get("validated")])
        completed_at = app_state.touch_last_run_time()

        summary = {
            "total": total,
            "processed": processed,
            "sent": sent,
            "query": query,
            "last_run_time": last_run_time,
            "completed_at": completed_at,
            "collected": len(collected),
            "deduped": len(deduped),
            "filtered": len(filtered),
            "published": len(publish_results),
            "issues": stored,
            "publish_results": publish_results,
        }
        app_state.update_result(summary)
        logger.info(
            "Pipeline finished: total=%s processed=%s sent=%s",
            summary["total"],
            summary["processed"],
            summary["sent"],
        )
        return summary

    def run_once(self, query: str = "한국 실시간 주요 이슈") -> dict[str, Any]:
        return self.run_pipeline(query=query)

    def _normalize_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(issue)
        normalized.setdefault("summary", "")
        normalized.setdefault("source", "unknown")
        normalized.setdefault("url", "")
        normalized.setdefault("collected_at", datetime.now(timezone.utc).isoformat())
        return normalized

    def _build_fallback_issue(self, query: str, stage: str) -> dict[str, Any]:
        return {
            "title": f"{query} fallback issue",
            "summary": f"{stage} 단계 실패로 생성된 더미 데이터입니다.",
            "source": "fallback",
            "url": f"https://example.com/fallback/{stage}",
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    def _fallback_analyzed_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        fallback = dict(issue)
        fallback.setdefault("analysis_model", "fallback")
        fallback["analysis_mode"] = "fallback"
        fallback["sentiment"] = fallback.get("sentiment", "unknown")
        fallback["priority"] = fallback.get("priority", "low")
        fallback["insight"] = fallback.get("insight", "분석 실패로 기본 인사이트를 적용했습니다.")
        return fallback

    def _fallback_validated_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        fallback = dict(issue)
        is_ok = bool(fallback.get("title") and fallback.get("url"))
        fallback["validation_status"] = "OK" if is_ok else "NO_OK"
        fallback["validated"] = is_ok
        return fallback

    def _build_fallback_message(self, issues: list[dict[str, Any]]) -> str:
        lines = ["실시간 이슈 분석 결과"]
        for index, issue in enumerate(issues, start=1):
            lines.append(f"{index}. {issue.get('title', 'unknown issue')}")
        return "\n".join(lines)

    def _deduplicate_issues(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for issue in issues:
            key = (issue.get("title", "").strip(), issue.get("url", "").strip())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(issue)
        return deduped

    def _filter_new_issues(
        self, issues: list[dict[str, Any]], last_run_time: str | None
    ) -> list[dict[str, Any]]:
        if not last_run_time:
            return issues
        try:
            baseline = datetime.fromisoformat(last_run_time)
        except ValueError:
            logger.warning("Invalid last_run_time format: %s", last_run_time)
            return issues
        if baseline.tzinfo is None:
            baseline = baseline.replace(tzinfo=timezone.utc)

        filtered: list[dict[str, Any]] = []
        for issue in issues:
            issue_time = self._parse_issue_time(issue)
            if issue_time is None or issue_time >= baseline:
                filtered.append(issue)
        return filtered

    def _parse_issue_time(self, issue: dict[str, Any]) -> datetime | None:
        for field in ("published_at", "collected_at", "created_at"):
            value = issue.get(field)
            if not value or not isinstance(value, str):
                continue
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                continue
        return None

    def _store_issues(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        stored: list[dict[str, Any]] = []
        logger.info("DB store started: input=%s", len(issues))
        for issue in issues:
            try:
                stored.append(db.save_issue(issue))
            except Exception as exc:  # pragma: no cover
                logger.exception("DB store failed: %s", exc)
                fallback = dict(issue)
                fallback.setdefault("id", None)
                fallback.setdefault("saved_at", datetime.now(timezone.utc).isoformat())
                stored.append(fallback)
        logger.info("DB store finished: stored=%s", len(stored))
        return stored


orchestrator = IssueMonitoringOrchestrator()
