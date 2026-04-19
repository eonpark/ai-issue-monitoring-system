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
from app.state import app_state

logger = logging.getLogger(__name__)


class IssueMonitoringOrchestrator:
    def __init__(self) -> None:
        self.analyzer = AnalyzerAgent()
        self.validator = ValidatorAgent()
        self.formatter = FormatterAgent()
        self.publisher = PublisherAgent()
        self.max_steps = 10

    def run_collector(self) -> list[dict[str, Any]]:
        logger.info("Collector step started")
        try:
            issues = collect_issues()
            logger.info("Collector step finished: count=%s", len(issues))
            return issues
        except Exception as exc:  # pragma: no cover
            logger.exception("Collector step failed: %s", exc)
            return []

    def run_analyzer(self, issues: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        issues = issues or []
        logger.info("Analyzer step started: count=%s", len(issues))
        try:
            analyzed = self.analyzer.analyze(issues)
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
            for issue in validated:
                issue["validation_status"] = "OK"
            invalid_urls = {item.get("url") for item in validated}
            for issue in issues:
                if issue.get("url") not in invalid_urls:
                    issue["validation_status"] = "NO_OK"
                    issue["validated"] = False
            logger.info("Validator step finished: count=%s", len(validated))
            return validated
        except Exception as exc:  # pragma: no cover
            logger.exception("Validator step failed: %s", exc)
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
        logger.info("LLM router pipeline started")
        state: dict[str, Any] = {
            "step": "start",
            "data": None,
            "message": None,
        }
        actions: list[str] = []
        publish_result: dict[str, Any] | None = None

        for step_index in range(1, self.max_steps + 1):
            decision = decide_next_action(state)
            action = decision.get("action", "end")
            actions.append(action)
            logger.info("Router decision: step_index=%s action=%s", step_index, action)

            if action == "collector":
                state["data"] = self.run_collector()
                state["step"] = "collector_done"
                state["issues"] = state["data"]

            elif action == "analyzer":
                state["data"] = self.run_analyzer(state.get("data"))
                state["step"] = "analyzer_done"
                state["issues"] = state["data"]
                state["analyzed"] = True

            elif action == "validator":
                state["data"] = self.run_validator(state.get("data"))
                state["step"] = "validator_done"
                state["issues"] = state["data"]
                state["validated"] = True

            elif action == "formatter":
                state["message"] = self.run_formatter(state.get("data"))
                state["step"] = "formatter_done"
                state["formatted"] = True

            elif action == "publisher":
                publish_result = self.run_publisher(state.get("message"))
                state["step"] = "publisher_done"
                state["published"] = True
                state["publish_result"] = publish_result

            elif action == "end":
                logger.info("Router requested end")
                break

            else:
                logger.warning("Unknown action received: %s", action)
                state["step"] = "error"
                break
        else:
            logger.warning("Max steps reached: %s", self.max_steps)

        summary = self._build_summary(state=state, actions=actions, publish_result=publish_result)
        app_state.update_result(summary)
        app_state.set_last_run_time(datetime.now(timezone.utc).isoformat())
        logger.info(
            "LLM router pipeline finished: final_step=%s total=%s sent=%s",
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
            "last_run_time": app_state.get_last_run_time(),
        }


orchestrator = IssueMonitoringOrchestrator()


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    print(orchestrator.run_pipeline())
