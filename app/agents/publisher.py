from __future__ import annotations

from app.skills.slack_send import send_message


class PublisherAgent:
    def publish(self, payload: dict) -> dict:
        return send_message(payload["text"])
