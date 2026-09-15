"""RAG retrieval: embed query → cosine top-k over KnowledgeChunk."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from apps.ai_agent.models import KnowledgeChunk
from apps.ai_agent.rag.embeddings import embed_text


@dataclass
class RetrievedChunk:
    chunk_id: int
    score: float
    text: str
    metadata: dict[str, Any]
    exception_id: int | None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def retrieve_similar(
    query_text: str,
    *,
    k: int = 5,
    exclude_exception_id: int | None = None,
    project_id: int | None = None,
) -> list[RetrievedChunk]:
    if not (query_text or "").strip():
        return []
    query_vec = embed_text(query_text)
    qs = KnowledgeChunk.objects.all()
    if project_id is not None:
        qs = qs.filter(project_id=project_id)
    scored: list[RetrievedChunk] = []
    for chunk in qs.iterator():
        if exclude_exception_id and chunk.exception_id == exclude_exception_id:
            continue
        vec = chunk.embedding or []
        score = _cosine(query_vec, vec)
        if score <= 0:
            continue
        scored.append(
            RetrievedChunk(
                chunk_id=chunk.pk,
                score=score,
                text=chunk.text,
                metadata=chunk.metadata or {},
                exception_id=chunk.exception_id,
            )
        )
    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:k]
