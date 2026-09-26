from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
SEMANTIC_SIMILARITY_MODEL = "openai/text-embedding-3-small"


def embed_texts(texts: list[str], *, api_key: str, timeout_seconds: float = 60.0) -> list[
    list[float]
] | None:
    """Embed short texts with OpenRouter (OpenAI-compatible endpoint).

    Both texts travel in one request. Returns None on any failure so
    callers can skip the question instead of failing the evaluation run.
    """
    cleaned = [(text or "")[:4000] for text in texts]
    if not any(item.strip() for item in cleaned):
        return None
    try:
        import httpx
    except ImportError:
        logger.warning("httpx is required for semantic similarity embeddings")
        return None
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                OPENROUTER_EMBEDDINGS_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": SEMANTIC_SIMILARITY_MODEL, "input": cleaned},
            )
        if response.status_code != 200:
            logger.warning("semantic embedding request failed status=%s", response.status_code)
            return None
        payload = response.json()
        items = sorted(payload.get("data", []), key=lambda row: row.get("index", 0))
        vectors = [row.get("embedding") for row in items]
        if len(vectors) != len(cleaned) or any(not vector for vector in vectors):
            return None
        return vectors
    except Exception:
        logger.warning("semantic embedding request failed", exc_info=True)
        return None
