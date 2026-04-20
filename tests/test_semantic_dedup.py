from __future__ import annotations

import unittest
from unittest.mock import patch

from app.semantic_dedup import deduplicate_with_db


class SemanticDedupTests(unittest.TestCase):
    @patch("app.semantic_dedup.get_recent_issues")
    @patch("app.semantic_dedup.OpenAI")
    def test_exact_url_duplicate_is_removed_before_semantic_compare(
        self,
        mock_openai,
        mock_recent_issues,
    ) -> None:
        mock_recent_issues.return_value = [
            {
                "url": "https://www.yna.co.kr/view/AKR20260416157600704",
                "summary": "기존 요약",
                "embedding": [0.1, 0.2, 0.3],
            }
        ]
        mock_openai.return_value = object()

        issues = [
            {
                "title": "중복 기사",
                "url": "https://www.yna.co.kr/view/AKR20260416157600704",
                "summary": "새 요약이라도 같은 URL",
            }
        ]

        deduped, stats = deduplicate_with_db(issues)

        self.assertEqual(deduped, [])
        self.assertEqual(stats, {"before": 1, "after": 0, "duplicates": 1})

    @patch("app.semantic_dedup.get_recent_issues")
    @patch("app.semantic_dedup._get_embedding")
    @patch("app.semantic_dedup.OpenAI")
    def test_new_url_is_kept_when_similarity_is_below_threshold(
        self,
        mock_openai,
        mock_get_embedding,
        mock_recent_issues,
    ) -> None:
        mock_recent_issues.return_value = [
            {
                "url": "https://example.com/old",
                "summary": "기존 요약",
                "embedding": [1.0, 0.0],
            }
        ]
        mock_openai.return_value = object()
        mock_get_embedding.return_value = [0.0, 1.0]

        issues = [
            {
                "title": "새 기사",
                "url": "https://example.com/new",
                "summary": "새 요약",
            }
        ]

        deduped, stats = deduplicate_with_db(issues)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["url"], "https://example.com/new")
        self.assertEqual(stats, {"before": 1, "after": 1, "duplicates": 0})


if __name__ == "__main__":
    unittest.main()
