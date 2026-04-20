from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = [
    "collector",
    "analyzer",
    "validator",
    "formatter",
    "publisher",
    "end",
]
DEFAULT_TRANSITIONS = {
    "start": "collector",
    "collector_done": "analyzer",
    "analyzer_done": "validator",
    "validator_done": "formatter",
    "formatter_done": "publisher",
    "publisher_done": "end",
}
FAILURE_FALLBACKS = {
    "collector": "end",
    "analyzer": "collector",
    "validator": "analyzer",
    "formatter": "validator",
    "publisher": "formatter",
}


def decide_next_action(state: dict[str, Any] | Any) -> dict[str, str]:
    """Return the next pipeline action from deterministic state transitions."""

    normalized_state = _normalize_state(state)
    action = _fallback_action(normalized_state)
    logger.info(
        "Router decided action=%s step=%s failed_action=%s",
        action,
        normalized_state.get("step"),
        normalized_state.get("failed_action"),
    )
    return {"action": action}


def _fallback_action(state: dict[str, Any]) -> str:
    failed_action = state.get("failed_action")
    if failed_action in ALLOWED_ACTIONS:
        attempts = state.get("retry_count", {}).get(failed_action, 0)
        max_retries = state.get("max_retries", {}).get(failed_action, 0)
        if attempts < max_retries:
            return failed_action
        return FAILURE_FALLBACKS.get(failed_action, "end")

    step = state.get("step")
    if step in DEFAULT_TRANSITIONS:
        return DEFAULT_TRANSITIONS[step]

    if not state.get("issues"):
        return "collector"
    if not state.get("analyzed"):
        return "analyzer"
    if not state.get("validated"):
        return "validator"
    if not state.get("formatted"):
        return "formatter"
    if not state.get("published"):
        return "publisher"
    return "end"


def _normalize_state(state: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(state, dict):
        return state
    if hasattr(state, "__dict__"):
        return dict(vars(state))
    return {"value": str(state)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    example_state = {
        "issues": [],
        "analyzed": False,
        "validated": False,
        "formatted": False,
        "published": False,
    }
    print(json.dumps(decide_next_action(example_state), ensure_ascii=False, indent=2))
