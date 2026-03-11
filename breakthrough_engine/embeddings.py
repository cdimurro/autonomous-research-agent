"""Embedding provider abstraction for the Breakthrough Engine.

Provides:
- EmbeddingProvider ABC
- OllamaEmbeddingProvider: local embeddings via Ollama
- MockEmbeddingProvider: deterministic embeddings for tests
- EmbeddingNoveltyEngine: semantic novelty layer

Phase 4B addition. Local-first design.
"""

from __future__ import annotations

import abc
import hashlib
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from .models import CandidateHypothesis, EvidenceItem, NoveltyResult, PriorArtHit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedding Provider ABC
# ---------------------------------------------------------------------------


class EmbeddingProvider(abc.ABC):
    """Abstract interface for text embedding."""

    @abc.abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of embedding vectors."""

    @abc.abstractmethod
    def dimension(self) -> int:
        """Return embedding dimension."""


# ---------------------------------------------------------------------------
# Mock Provider (for tests)
# ---------------------------------------------------------------------------


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic mock embeddings based on text hashing.

    Produces reproducible embeddings that preserve some similarity structure:
    texts sharing words will have somewhat similar embeddings.
    """

    def __init__(self, dim: int = 64):
        self._dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    def dimension(self) -> int:
        return self._dim

    def _hash_embed(self, text: str) -> list[float]:
        """Produce a deterministic pseudo-embedding from text hash."""
        # Use word-level hashing so similar texts get somewhat similar vectors
        words = text.lower().split()
        vec = [0.0] * self._dim
        for word in words:
            h = hashlib.md5(word.encode()).hexdigest()
            for i in range(self._dim):
                byte_val = int(h[i % len(h)], 16)
                vec[i] += (byte_val - 7.5) / 7.5  # normalize to ~[-1, 1]
        # Normalize
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


# ---------------------------------------------------------------------------
# Ollama Embedding Provider
# ---------------------------------------------------------------------------


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Local embeddings via Ollama API.

    Default model: qwen3-embedding:4b (2560d, top MTEB quality, runs locally).
    Falls back gracefully if Ollama is unavailable.
    """

    def __init__(
        self,
        host: str = "127.0.0.1:11434",
        model: str = "qwen3-embedding:4b",
        dim: int = 2560,
        timeout: int = 120,
    ):
        import os
        self.host = os.environ.get("OLLAMA_HOST", host)
        self.model = os.environ.get("BT_EMBEDDING_MODEL", model)
        self._dim = dim
        self.timeout = timeout
        self._available: Optional[bool] = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        import requests
        url = f"http://{self.host}/api/embed"

        try:
            resp = requests.post(
                url,
                json={"model": self.model, "input": texts, "keep_alive": -1},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings and len(embeddings) == len(texts):
                self._available = True
                self._dim = len(embeddings[0])
                return embeddings
            logger.warning("Ollama embedding returned unexpected shape")
            return []
        except Exception as e:
            if self._available is None:
                logger.info("Ollama embedding not available: %s (will use fallback)", e)
                self._available = False
            return []

    def dimension(self) -> int:
        return self._dim

    def is_available(self) -> bool:
        """Check if Ollama embedding endpoint is reachable."""
        if self._available is not None:
            return self._available
        # Probe with a small request
        result = self.embed(["test"])
        return self._available or False


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Embedding Novelty Result
# ---------------------------------------------------------------------------

@dataclass
class EmbeddingNoveltyDetail:
    """Additional novelty details from embedding analysis."""
    embedding_similarity_max: float = 0.0
    nearest_neighbors: list[dict] = field(default_factory=list)  # [{title, similarity, source}]
    novelty_basis: str = "lexical_only"  # "lexical_only", "embedding_assisted", "embedding_primary"
    blocked_by_prior_art: bool = False

    def to_dict(self) -> dict:
        return {
            "embedding_similarity_max": round(self.embedding_similarity_max, 4),
            "nearest_neighbors": self.nearest_neighbors[:5],
            "novelty_basis": self.novelty_basis,
            "blocked_by_prior_art": self.blocked_by_prior_art,
        }


# ---------------------------------------------------------------------------
# Embedding Novelty Engine
# ---------------------------------------------------------------------------

class EmbeddingNoveltyEngine:
    """Semantic novelty layer using embeddings.

    Works alongside the lexical NoveltyEngine. This engine:
    1. Embeds the candidate (title + statement + mechanism)
    2. Embeds prior candidates and retrieved evidence
    3. Computes cosine similarities
    4. Flags semantic near-duplicates that lexical methods miss
    """

    def __init__(
        self,
        provider: EmbeddingProvider,
        similarity_threshold: float = 0.88,
        warn_threshold: float = 0.78,
    ):
        self.provider = provider
        self.similarity_threshold = similarity_threshold
        self.warn_threshold = warn_threshold

    def evaluate(
        self,
        candidate: CandidateHypothesis,
        prior_texts: list[dict],  # [{title, text, source, source_id}]
        retrieved_evidence: list[EvidenceItem] | None = None,
    ) -> EmbeddingNoveltyDetail:
        """Run embedding-based novelty analysis."""
        detail = EmbeddingNoveltyDetail()

        cand_text = f"{candidate.title}. {candidate.statement}. {candidate.mechanism}"

        # Build comparison corpus
        corpus: list[dict] = list(prior_texts)
        if retrieved_evidence:
            for ev in retrieved_evidence:
                corpus.append({
                    "title": ev.title,
                    "text": f"{ev.title}. {ev.quote}",
                    "source": "retrieved_paper",
                    "source_id": ev.source_id,
                })

        if not corpus:
            detail.novelty_basis = "embedding_assisted"
            return detail

        # Embed candidate and corpus
        texts_to_embed = [cand_text] + [c["text"] for c in corpus]
        embeddings = self.provider.embed(texts_to_embed)

        if not embeddings or len(embeddings) < 2:
            # Embedding failed — fall back to lexical only
            detail.novelty_basis = "lexical_only"
            return detail

        cand_emb = embeddings[0]
        corpus_embs = embeddings[1:]

        detail.novelty_basis = "embedding_assisted"

        # Compare against each corpus item
        max_sim = 0.0
        neighbors: list[dict] = []

        for i, (corp, corp_emb) in enumerate(zip(corpus, corpus_embs)):
            sim = cosine_similarity(cand_emb, corp_emb)
            if sim > max_sim:
                max_sim = sim

            if sim >= self.warn_threshold:
                neighbors.append({
                    "title": corp["title"][:100],
                    "similarity": round(sim, 4),
                    "source": corp["source"],
                })

        detail.embedding_similarity_max = max_sim
        # Sort neighbors by similarity descending
        neighbors.sort(key=lambda x: x["similarity"], reverse=True)
        detail.nearest_neighbors = neighbors[:5]

        if max_sim >= self.similarity_threshold:
            detail.blocked_by_prior_art = True
            logger.info(
                "Embedding novelty BLOCK for '%s': max_sim=%.3f >= %.3f",
                candidate.title[:40], max_sim, self.similarity_threshold,
            )

        return detail
