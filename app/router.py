from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
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
    """Decide the next pipeline action from agents/skills docs and current state."""

    normalized_state = _normalize_state(state)
    if _should_use_local_transition(normalized_state):
        action = _fallback_action(normalized_state)
        logger.info("Router local transition action=%s", action)
        return {"action": action}

    agents_md = _read_text_file(Path("agents.md"))
    skills_md = _read_text_file(Path("skills.md"))

    if not agents_md or not skills_md:
        logger.warning("Router fallback applied: missing agents.md or skills.md")
        return {"action": _fallback_action(normalized_state)}

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning("Router fallback applied: missing OPENAI_API_KEY")
        return {"action": _fallback_action(normalized_state)}

    try:
        payload = _build_openai_payload(
            agents_md=agents_md,
            skills_md=skills_md,
            state=normalized_state,
        )
        response = requests.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        response_json = response.json()
        action = _extract_action(response_json, normalized_state)
        logger.info("Router decided action=%s", action)
        return {"action": action}
    except requests.HTTPError as exc:  # pragma: no cover
        if exc.response is not None and exc.response.status_code == 429:
            logger.warning("Router rate-limited, using fallback")
        else:
            logger.exception("Router failed, using fallback: %s", exc)
        return {"action": _fallback_action(normalized_state)}
    except Exception as exc:  # pragma: no cover
        logger.exception("Router failed, using fallback: %s", exc)
        return {"action": _fallback_action(normalized_state)}


def _build_openai_payload(
    agents_md: str,
    skills_md: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    transition_rules = {
        **DEFAULT_TRANSITIONS,
    }
    current_step = state.get("step", "start")
    expected_action = transition_rules.get(current_step, _fallback_action(state))

    instructions = (
        "You are a strict router for an LLM-based agent system. "
        "You must decide the next action from the current step transition rules and failure recovery rules. "
        "Allowed actions are exactly: collector, analyzer, validator, formatter, publisher, end. "
        "You must return JSON only. "
        "Do not include explanations, markdown, prose, code fences, or extra keys. "
        "Return exactly one JSON object with a single key named action."
    )

    user_prompt = (
        "Decide the next action for the pipeline.\n\n"
        "Transition rules:\n"
        '- start -> collector\n'
        '- collector_done -> analyzer\n'
        '- analyzer_done -> validator\n'
        '- validator_done -> formatter\n'
        '- formatter_done -> publisher\n'
        '- publisher_done -> end\n\n'
        "Failure recovery rules:\n"
        "- If the last action failed and retry_count is still below max_retries for that action, retry the same action.\n"
        "- If collector keeps failing after retries, choose end.\n"
        "- If analyzer keeps failing after retries, go back to collector.\n"
        "- If validator keeps failing after retries, go back to analyzer.\n"
        "- If formatter keeps failing after retries, go back to validator.\n"
        "- If publisher keeps failing after retries, go back to formatter.\n\n"
        f"Current step: {current_step}\n"
        f"Expected next action from the rules: {expected_action}\n\n"
        f"Allowed actions: {ALLOWED_ACTIONS}\n\n"
        "Output requirements:\n"
        '- Return JSON only\n'
        '- Format must be exactly: {"action": "<one_allowed_action>"}\n'
        "- Do not output any text before or after the JSON\n\n"
        f"Current state:\n{json.dumps(state, ensure_ascii=False, indent=2)}\n\n"
        f"agents.md:\n{agents_md}\n\n"
        f"skills.md:\n{skills_md}\n"
    )

    return {
        "model": DEFAULT_MODEL,
        "instructions": instructions,
        "input": user_prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "next_action",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ALLOWED_ACTIONS,
                        }
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
            }
        },
    }


def _extract_action(response_json: dict[str, Any], state: dict[str, Any]) -> str:
    candidates: list[str] = []

    output_text = response_json.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        candidates.append(output_text)

    for item in response_json.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                candidates.append(text)

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        action = data.get("action")
        if action in ALLOWED_ACTIONS and _is_valid_for_step(state, action):
            return action

    raise ValueError("No valid action found in OpenAI response")


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


def _is_valid_for_step(state: dict[str, Any], action: str) -> bool:
    return action == _fallback_action(state)


def _should_use_local_transition(state: dict[str, Any]) -> bool:
    failed_action = state.get("failed_action")
    if failed_action in ALLOWED_ACTIONS:
        return True
    return state.get("step") in DEFAULT_TRANSITIONS


def _normalize_state(state: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(state, dict):
        return state
    if hasattr(state, "__dict__"):
        return dict(vars(state))
    return {"value": str(state)}


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Router file not found: %s", path)
        return ""


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
