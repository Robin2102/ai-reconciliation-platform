"""Text → dense vector for similarity search."""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from django.conf import settings

_TOKEN = re.compile(r"[a-z0-9]+", re.I)


def embedding_dimension() -> int:
    return int(getattr(settings, "RAG_EMBEDDING_DIM", 384))


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def fake_embed(text: str, dim: int | None = None) -> list[float]:
    """Deterministic bag-of-tokens vector (tests + dev without ML deps)."""
    dim = dim or embedding_dimension()
    vec = [0.0] * dim
    for token in _TOKEN.findall((text or "").lower()):
        idx = int(hashlib.sha256(token.encode()).hexdigest(), 16) % dim
        vec[idx] += 1.0
    return _normalize(vec)


@lru_cache(maxsize=1)
def _sentence_transformer():
    from sentence_transformers import SentenceTransformer

    model_name = getattr(settings, "RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    return SentenceTransformer(model_name)


def sentence_transformer_embed(text: str) -> list[float]:
    model = _sentence_transformer()
    vec = model.encode(text or "", normalize_embeddings=True)
    return [float(x) for x in vec]


def embed_text(text: str) -> list[float]:
    backend = (getattr(settings, "RAG_EMBEDDING_BACKEND", "fake") or "fake").strip().lower()
    if backend == "sentence_transformers":
        try:
            return sentence_transformer_embed(text)
        except Exception:
            pass
    return fake_embed(text)
