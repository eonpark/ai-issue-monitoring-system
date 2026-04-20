from __future__ import annotations

import unittest

from app.router import decide_next_action


class RouterStateTransitionTests(unittest.TestCase):
    def test_start_transitions_to_collector(self) -> None:
        state = {
            "step": "start",
            "issues": [],
            "analyzed": False,
            "validated": False,
            "formatted": False,
            "published": False,
            "failed_action": None,
            "retry_count": {},
            "max_retries": {},
        }

        self.assertEqual(decide_next_action(state), {"action": "collector"})

    def test_happy_path_transition_uses_default_sequence(self) -> None:
        state = {
            "step": "analyzer_done",
            "issues": [{"title": "sample"}],
            "analyzed": True,
            "validated": False,
            "formatted": False,
            "published": False,
            "failed_action": None,
            "retry_count": {},
            "max_retries": {},
        }

        self.assertEqual(decide_next_action(state), {"action": "validator"})

    def test_failed_action_retries_same_step_before_limit(self) -> None:
        state = {
            "step": "collector_failed",
            "issues": [],
            "analyzed": False,
            "validated": False,
            "formatted": False,
            "published": False,
            "failed_action": "collector",
            "retry_count": {"collector": 1},
            "max_retries": {"collector": 2},
        }

        self.assertEqual(decide_next_action(state), {"action": "collector"})

    def test_failed_collector_falls_back_to_end_after_retry_limit(self) -> None:
        state = {
            "step": "collector_failed",
            "issues": [],
            "analyzed": False,
            "validated": False,
            "formatted": False,
            "published": False,
            "failed_action": "collector",
            "retry_count": {"collector": 2},
            "max_retries": {"collector": 2},
        }

        self.assertEqual(decide_next_action(state), {"action": "end"})

    def test_failed_analyzer_falls_back_to_collector_after_retry_limit(self) -> None:
        state = {
            "step": "analyzer_failed",
            "issues": [{"title": "sample"}],
            "analyzed": False,
            "validated": False,
            "formatted": False,
            "published": False,
            "failed_action": "analyzer",
            "retry_count": {"analyzer": 1},
            "max_retries": {"analyzer": 1},
        }

        self.assertEqual(decide_next_action(state), {"action": "collector"})


if __name__ == "__main__":
    unittest.main()
