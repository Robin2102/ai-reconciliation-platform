"""Agent tools — plain functions callable with or without an LLM."""

from __future__ import annotations

from apps.ai_agent.rag.retriever import RetrievedChunk, retrieve_similar


def retrieve_similar_past_cases(
    query_text: str,
    *,
    k: int = 5,
    exclude_exception_id: int | None = None,
    project_id: int | None = None,
) -> list[RetrievedChunk]:
    return retrieve_similar(
        query_text,
        k=k,
        exclude_exception_id=exclude_exception_id,
        project_id=project_id,
    )
