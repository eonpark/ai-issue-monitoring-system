from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.skills.slack_send import send_to_slack

logger = logging.getLogger(__name__)


def publish(message: str) -> dict[str, Any]:
    try:
        result = send_to_slack(message)
    except Exception as exc:  # pragma: no cover
        logger.exception("Publisher failed: %s", exc)
        logger.info("Publisher: sent=%s", 0)
        return {"status": "failed", "detail": str(exc), "message": message}

    sent = 1 if result.get("status") == "sent" else 0
    logger.info("Publisher: sent=%s", sent)
    return result


class PublisherAgent:
    def publish(self, payload: dict[str, Any]) -> dict[str, Any]:
        return publish(str(payload.get("text", "")))


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    print(publish("test message"))
