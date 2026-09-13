"""
CONCEPT TO LEARN: the Strategy pattern — this is the heart of a reconciliation
engine. The engine doesn't care HOW two records are matched, only that
every strategy exposes the same `match(a, b) -> MatchScore` interface.

Notice the last strategy is where NLP/embeddings enters the picture later —
same interface, smarter internals. That's the point of the pattern.
"""
from abc import ABC, abstractmethod


class MatchStrategy(ABC):
    @abstractmethod
    def match(self, record_a, record_b) -> float:
        """Return a confidence score 0.0-1.0. TODO (together)."""
        raise NotImplementedError


class ExactMatchStrategy(MatchStrategy):
    """TODO (together): exact match on external_ref + amount + currency."""
    def match(self, record_a, record_b) -> float:
        ...


class FuzzyMatchStrategy(MatchStrategy):
    """TODO (together, later): fuzzy match on description/amount tolerance."""
    def match(self, record_a, record_b) -> float:
        ...


class EmbeddingMatchStrategy(MatchStrategy):
    """TODO (together, once we reach the RAG/NLP module): match using
    semantic similarity of free-text fields via embeddings, not exact rules."""
    def match(self, record_a, record_b) -> float:
        ...
