from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

load_dotenv()


def send_to_slack(message: str) -> dict[str, str]:
    """Send a message to Slack webhook and return the delivery result."""

    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        return {
            "status": "skipped",
            "detail": "Slack webhook not configured.",
            "message": message,
        }

    try:
        response = requests.post(
            webhook,
            json={"text": message},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
    except requests.RequestException as exc:  # pragma: no cover
        return {
            "status": "failed",
            "detail": f"Slack request failed: {exc}",
            "message": message,
        }

    if response.status_code == 200 and response.text.strip().lower() == "ok":
        return {
            "status": "sent",
            "detail": "Slack message sent successfully.",
            "message": message,
        }

    return {
        "status": "failed",
        "detail": f"Slack webhook error: status={response.status_code} body={response.text.strip()}",
        "message": message,
    }


def send_message(message: str) -> dict[str, str]:
    """Backward-compatible alias."""

    return send_to_slack(message)
