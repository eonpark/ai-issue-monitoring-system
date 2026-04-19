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


def decide_next_action(state: dict[str, Any] | Any) -> dict[str, str]:
    """Decide the next pipeline action from agents/skills docs and current state."""

    normalized_state = _normalize_state(state)
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
    except Exception as exc:  # pragma: no cover
        logger.exception("Router failed, using fallback: %s", exc)
        return {"action": _fallback_action(normalized_state)}


def _build_openai_payload(
    agents_md: str,
    skills_md: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    transition_rules = {
        "start": "collector",
        "collector_done": "analyzer",
        "analyzer_done": "validator",
        "validator_done": "formatter",
        "formatter_done": "publisher",
        "publisher_done": "end",
    }
    current_step = state.get("step", "start")
    expected_action = transition_rules.get(current_step, _fallback_action(state))

    instructions = (
        "You are a strict router for an LLM-based agent system. "
        "You must decide the next action only from the current step transition rules. "
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
    step = state.get("step")
    if step == "start":
        return "collector"
    if step == "collector_done":
        return "analyzer"
    if step == "analyzer_done":
        return "validator"
    if step == "validator_done":
        return "formatter"
    if step == "formatter_done":
        return "publisher"
    if step == "publisher_done":
        return "end"

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
    expected = {
        "start": "collector",
        "collector_done": "analyzer",
        "analyzer_done": "validator",
        "validator_done": "formatter",
        "formatter_done": "publisher",
        "publisher_done": "end",
    }
    current_step = state.get("step")
    if current_step in expected:
        return expected[current_step] == action
    return action == _fallback_action(state)


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
