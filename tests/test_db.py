from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import app.db as db


class DatabasePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._original_db_path = db.DB_PATH
        db.DB_PATH = Path(self._temp_dir.name) / "test_issues.db"

    def tearDown(self) -> None:
        db.DB_PATH = self._original_db_path
        self._temp_dir.cleanup()

    def test_save_and_restore_run_result(self) -> None:
        result = {
            "final_step": "publisher_done",
            "actions": ["collector", "analyzer", "validator", "formatter", "publisher", "end"],
            "total": 2,
            "processed": 2,
            "sent": 1,
            "message": "test message",
            "publish_result": {"status": "sent", "detail": "ok"},
            "dedup": {"before": 3, "after": 2, "duplicates": 1},
            "metrics": {"collection": {"collector_count": 2}},
            "last_error": None,
            "last_run_time": "2026-04-21T00:00:00+00:00",
        }

        run_id = db.save_run_result(result)
        saved = db.get_last_run()

        self.assertIsInstance(run_id, int)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["id"], run_id)
        self.assertEqual(saved["final_step"], "publisher_done")
        self.assertEqual(saved["actions"], result["actions"])
        self.assertEqual(saved["message"], "test message")
        self.assertEqual(saved["dedup"], {"before": 3, "after": 2, "duplicates": 1})
        self.assertEqual(saved["metrics"], {"collection": {"collector_count": 2}})
        self.assertEqual(saved["publish_result"]["status"], "sent")
        self.assertEqual(saved["publish_result"]["detail"], "ok")

    def test_save_and_load_issues_by_run_id(self) -> None:
        run_id = db.save_run_result(
            {
                "final_step": "validator_done",
                "actions": ["collector", "analyzer", "validator"],
                "total": 2,
                "processed": 2,
                "sent": 0,
                "message": None,
                "publish_result": None,
                "dedup": {"before": 2, "after": 2, "duplicates": 0},
                "metrics": {},
                "last_error": None,
                "last_run_time": "2026-04-21T00:00:00+00:00",
            }
        )
        issues = [
            {
                "title": "Issue A",
                "summary": "Summary A",
                "score": 78,
                "status": "OK",
                "issue_type": "event",
                "impact_scope": "regional",
                "change_nature": "concrete_change",
                "major_issue": True,
                "validation_reason": "정책 방향성 이슈",
                "embedding": [0.1, 0.2, 0.3],
                "url": "https://example.com/a",
            },
            {
                "title": "Issue B",
                "summary": "Summary B",
                "score": 44,
                "status": "NO_OK",
                "issue_type": "signal",
                "impact_scope": "limited",
                "change_nature": "commentary",
                "major_issue": False,
                "validation_reason": "중요도 낮음 또는 영향도 제한적",
                "embedding": [0.4, 0.5],
                "url": "https://example.com/b",
            },
        ]

        saved_count = db.save_issues(issues, run_id=run_id)
        loaded = db.get_issues(run_id=run_id)

        self.assertEqual(saved_count, 2)
        self.assertEqual(len(loaded), 2)
        self.assertEqual({item["run_id"] for item in loaded}, {run_id})

        latest = loaded[0]
        self.assertIn(latest["title"], {"Issue A", "Issue B"})
        loaded_by_title = {item["title"]: item for item in loaded}
        self.assertEqual(loaded_by_title["Issue A"]["embedding"], [0.1, 0.2, 0.3])
        self.assertEqual(loaded_by_title["Issue B"]["embedding"], [0.4, 0.5])
        self.assertTrue(loaded_by_title["Issue A"]["major_issue"])
        self.assertFalse(loaded_by_title["Issue B"]["major_issue"])

    def test_get_recent_issues_returns_only_recent_rows(self) -> None:
        db.save_issues(
            [
                {
                    "title": "Recent Issue",
                    "summary": "Recent Summary",
                    "score": 70,
                    "status": "OK",
                    "issue_type": "event",
                    "impact_scope": "global",
                    "change_nature": "concrete_change",
                    "major_issue": True,
                    "validation_reason": "정책 방향성 이슈",
                    "embedding": [0.9],
                    "url": "https://example.com/recent",
                }
            ]
        )

        recent = db.get_recent_issues(days=3, limit=10)

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["title"], "Recent Issue")

    def test_empty_inputs_are_handled_safely(self) -> None:
        self.assertIsNone(db.save_run_result(None))
        self.assertEqual(db.save_issues([]), 0)
        self.assertEqual(db.save_issues(None), 0)

    def test_invalid_issue_rows_are_skipped(self) -> None:
        issues = [
            {
                "title": "",
                "summary": "Missing title",
                "score": 10,
                "status": "NO_OK",
                "url": "https://example.com/missing-title",
            },
            {
                "title": "Missing URL",
                "summary": "Missing url",
                "score": 10,
                "status": "NO_OK",
                "url": "",
            },
            {
                "title": "Valid Issue",
                "summary": "Valid summary",
                "score": 80,
                "status": "OK",
                "issue_type": "event",
                "impact_scope": "regional",
                "change_nature": "concrete_change",
                "major_issue": True,
                "validation_reason": "정책 방향성 이슈",
                "embedding": [1.0],
                "url": "https://example.com/valid",
            },
        ]

        saved_count = db.save_issues(issues)
        loaded = db.get_issues()

        self.assertEqual(saved_count, 1)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["title"], "Valid Issue")


if __name__ == "__main__":
    unittest.main()
