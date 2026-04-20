from __future__ import annotations

import logging
import math
from typing import Any

from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

from app.db import get_recent_issues

load_dotenv()

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
SIMILARITY_THRESHOLD = 0.85
RECENT_DAYS = 3
RECENT_LIMIT = 200


def deduplicate_with_db(issues: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not issues:
        stats = {"before": 0, "after": 0, "duplicates": 0}
        logger.info("DB Semantic Dedup: before=%s after=%s duplicates=%s", 0, 0, 0)
        return [], stats

    if OpenAI is None:
        logger.warning("DB Semantic Dedup skipped: openai package is unavailable")
        stats = {"before": len(issues), "after": len(issues), "duplicates": 0}
        return issues, stats

    try:
        client = OpenAI()
    except Exception as exc:  # pragma: no cover
        logger.exception("DB Semantic Dedup skipped: embedding client init failed: %s", exc)
        stats = {"before": len(issues), "after": len(issues), "duplicates": 0}
        return issues, stats

    try:
        recent_issues = get_recent_issues(days=RECENT_DAYS, limit=RECENT_LIMIT)
    except Exception as exc:  # pragma: no cover
        logger.exception("DB Semantic Dedup skipped: recent issue load failed: %s", exc)
        stats = {"before": len(issues), "after": len(issues), "duplicates": 0}
        return issues, stats

    embedding_cache: dict[str, list[float]] = {}
    recent_urls = _prepare_recent_url_set(recent_issues)
    recent_vectors = _prepare_recent_vectors(client, recent_issues, embedding_cache)

    deduped: list[dict[str, Any]] = []
    duplicate_count = 0

    for issue in issues:
        normalized_url = _normalized_url(issue.get("url"))
        if normalized_url and normalized_url in recent_urls:
            duplicate_count += 1
            continue

        summary = _summary_text(issue)
        if not summary:
            deduped.append(issue)
            if normalized_url:
                recent_urls.add(normalized_url)
            continue

        new_embedding = _get_embedding(client, summary, embedding_cache)
        if not new_embedding:
            deduped.append(issue)
            if normalized_url:
                recent_urls.add(normalized_url)
            continue

        is_duplicate = False
        for recent_issue in recent_vectors:
            similarity = _cosine_similarity(new_embedding, recent_issue["embedding"])
            if similarity > SIMILARITY_THRESHOLD:
                is_duplicate = True
                break

        if is_duplicate:
            duplicate_count += 1
            continue

        deduped_issue = {**issue, "embedding": new_embedding}
        deduped.append(deduped_issue)
        if normalized_url:
            recent_urls.add(normalized_url)
        recent_vectors.append({"embedding": new_embedding})

    logger.info(
        "DB Semantic Dedup: before=%s after=%s duplicates=%s",
        len(issues),
        len(deduped),
        duplicate_count,
    )
    return deduped, {"before": len(issues), "after": len(deduped), "duplicates": duplicate_count}


def _prepare_recent_url_set(recent_issues: list[dict[str, Any]]) -> set[str]:
    urls: set[str] = set()
    for issue in recent_issues:
        normalized_url = _normalized_url(issue.get("url"))
        if normalized_url:
            urls.add(normalized_url)
    return urls


def _prepare_recent_vectors(
    client: OpenAI,
    recent_issues: list[dict[str, Any]],
    embedding_cache: dict[str, list[float]],
) -> list[dict[str, list[float]]]:
    vectors: list[dict[str, list[float]]] = []
    for issue in recent_issues:
        embedding = issue.get("embedding")
        if isinstance(embedding, list) and embedding:
            vectors.append({"embedding": embedding})
            continue

        summary = _summary_text(issue)
        if not summary:
            continue
        generated_embedding = _get_embedding(client, summary, embedding_cache)
        if generated_embedding:
            vectors.append({"embedding": generated_embedding})
    return vectors


def _get_embedding(
    client: OpenAI,
    text: str,
    embedding_cache: dict[str, list[float]],
) -> list[float]:
    cached = embedding_cache.get(text)
    if cached:
        return cached

    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    embedding = response.data[0].embedding if response.data else []
    normalized = [float(item) for item in embedding] if embedding else []
    if normalized:
        embedding_cache[text] = normalized
    return normalized


def _summary_text(issue: dict[str, Any]) -> str:
    return str(issue.get("summary", "")).strip()


def _normalized_url(value: Any) -> str:
    return str(value or "").strip()


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)
