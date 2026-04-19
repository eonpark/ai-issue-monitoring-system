from __future__ import annotations

import os


def send_message(message: str) -> dict[str, str]:
    """Stub Slack sender that reports whether a webhook is configured."""

    webhook = os.getenv("SLACK_WEBHOOK_URL", "")
    status = "sent" if webhook else "skipped"
    detail = "Slack webhook configured." if webhook else "Slack webhook not configured."
    return {"status": status, "detail": detail, "message": message}
