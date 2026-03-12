"""Paper ingestion and segment staging for the KG shadow foundation.

Phase 10A: Ingests papers from upstream sources (findings table, retrieval
cache) into bt_paper_segments for downstream entity/relation extraction.

Segments are:
- abstract (segment_index=0)
- bounded text chunks (segment_index=1..N) if full text is available

Segment relevance is scored using embedding similarity to a domain anchor.
Compression is optional and uses the local Ollama stack.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from .db import Repository
from .embeddings import EmbeddingProvider, cosine_similarity
from .models import new_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_SEGMENT_MAX_CHARS = 2000
_DEFAULT_MIN_RELEVANCE = 0.1


@dataclass
class IngestionConfig:
    """Configuration for the paper ingestion worker."""
    domain: str = "clean-energy"
    limit: int = 100
    segment_max_chars: int = _DEFAULT_SEGMENT_MAX_CHARS
    min_relevance: float = _DEFAULT_MIN_RELEVANCE
    compress: bool = False
    ollama_host: str = "127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b-q4_K_M"
    ollama_timeout: int = 120


# ---------------------------------------------------------------------------
# Segmenter
# ---------------------------------------------------------------------------

def segment_text(text: str, max_chars: int = _DEFAULT_SEGMENT_MAX_CHARS) -> list[str]:
    """Split text into bounded segments.

    Strategy: split on paragraph breaks first, then on sentence boundaries
    if a paragraph exceeds max_chars.
    """
    if not text or not text.strip():
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    segments: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            segments.append(para)
        else:
            # Split on sentence boundaries
            sentences = _split_sentences(para)
            if len(sentences) <= 1:
                # No sentence boundaries — hard-split by char limit
                for i in range(0, len(para), max_chars):
                    segments.append(para[i:i + max_chars])
            else:
                current: list[str] = []
                current_len = 0
                for sent in sentences:
                    if current_len + len(sent) + 1 > max_chars and current:
                        segments.append(" ".join(current))
                        current = []
                        current_len = 0
                    current.append(sent)
                    current_len += len(sent) + 1
                if current:
                    segments.append(" ".join(current))

    return segments


def _split_sentences(text: str) -> list[str]:
    """Simple sentence splitter."""
    import re
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Relevance scorer
# ---------------------------------------------------------------------------

class SegmentRelevanceScorer:
    """Scores segment relevance using embedding similarity to a domain anchor."""

    def __init__(self, provider: EmbeddingProvider, domain_anchor: str = ""):
        self.provider = provider
        self._anchor_embedding: Optional[list[float]] = None
        self._domain_anchor = domain_anchor

    def _get_anchor(self, domain: str) -> list[float]:
        if self._anchor_embedding is not None:
            return self._anchor_embedding
        anchor_text = self._domain_anchor or f"scientific research breakthrough in {domain}"
        result = self.provider.embed([anchor_text])
        if result:
            self._anchor_embedding = result[0]
            return self._anchor_embedding
        return []

    def score(self, text: str, domain: str) -> float:
        """Return relevance score [0, 1] for text vs domain anchor."""
        anchor = self._get_anchor(domain)
        if not anchor:
            return 0.5  # fallback when embeddings unavailable

        result = self.provider.embed([text])
        if not result:
            return 0.5

        return max(0.0, min(1.0, cosine_similarity(anchor, result[0])))

    def score_batch(self, texts: list[str], domain: str) -> list[float]:
        """Score multiple texts at once."""
        if not texts:
            return []
        anchor = self._get_anchor(domain)
        if not anchor:
            return [0.5] * len(texts)

        embeddings = self.provider.embed(texts)
        if not embeddings or len(embeddings) != len(texts):
            return [0.5] * len(texts)

        return [
            max(0.0, min(1.0, cosine_similarity(anchor, emb)))
            for emb in embeddings
        ]


# ---------------------------------------------------------------------------
# Compressor (optional, uses Ollama)
# ---------------------------------------------------------------------------

def compress_segment(
    text: str,
    host: str = "127.0.0.1:11434",
    model: str = "qwen3.5:9b-q4_K_M",
    timeout: int = 120,
) -> str:
    """Compress a segment into a concise summary using local Ollama.

    Returns the original text if compression fails.
    """
    import requests

    prompt = (
        "Summarize the following scientific text into 2-3 concise sentences "
        "preserving key findings, mechanisms, and quantitative results. "
        "Return ONLY the summary, no preamble.\n\n"
        f"TEXT:\n{text[:3000]}"
    )

    try:
        resp = requests.post(
            f"http://{host}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "options": {"num_predict": 512, "temperature": 0.3},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        return content.strip() if content.strip() else text
    except Exception as e:
        logger.warning("Segment compression failed: %s", e)
        return text


# ---------------------------------------------------------------------------
# Ingestion worker
# ---------------------------------------------------------------------------

class PaperIngestionWorker:
    """Ingests papers from upstream sources into bt_paper_segments.

    Sources:
    1. findings table (scires.db upstream)
    2. bt_evidence_items from prior runs
    """

    def __init__(
        self,
        repo: Repository,
        embedding_provider: Optional[EmbeddingProvider] = None,
        config: Optional[IngestionConfig] = None,
    ):
        self.repo = repo
        self.config = config or IngestionConfig()
        self._scorer = (
            SegmentRelevanceScorer(embedding_provider)
            if embedding_provider
            else None
        )

    def ingest_from_findings(self, domain: str = "", limit: int = 0) -> dict:
        """Ingest papers from the upstream findings table.

        Returns a summary dict of the ingestion run.
        """
        domain = domain or self.config.domain
        limit = limit or self.config.limit

        stats = {"ingested": 0, "skipped": 0, "errors": 0, "domain": domain}

        try:
            rows = self.repo.db.execute(
                """SELECT DISTINCT p.paper_id, p.title, p.arxiv_id, p.doi,
                          f.content, f.provenance_quote
                   FROM findings f
                   JOIN papers p ON f.paper_id = p.paper_id
                   WHERE (p.subjects LIKE ? OR p.title LIKE ? OR f.content LIKE ?)
                     AND f.judge_verdict = 'accepted'
                   ORDER BY f.confidence DESC
                   LIMIT ?""",
                (f"%{domain}%", f"%{domain}%", f"%{domain}%", limit),
            ).fetchall()
        except Exception as e:
            logger.warning("Cannot query upstream findings: %s", e)
            rows = []

        for row in rows:
            try:
                self._ingest_paper_row(row, domain)
                stats["ingested"] += 1
            except Exception as e:
                logger.warning("Ingestion error for paper %s: %s", row[0], e)
                stats["errors"] += 1

        logger.info(
            "PaperIngestionWorker: domain=%s ingested=%d skipped=%d errors=%d",
            domain, stats["ingested"], stats["skipped"], stats["errors"],
        )
        return stats

    def ingest_from_evidence_items(self, domain: str = "", limit: int = 0) -> dict:
        """Ingest from bt_evidence_items collected in prior runs."""
        domain = domain or self.config.domain
        limit = limit or self.config.limit

        stats = {"ingested": 0, "skipped": 0, "errors": 0, "domain": domain}

        try:
            rows = self.repo.db.execute(
                """SELECT ei.id, ei.source_id, ei.title, ei.quote, ei.source_type
                   FROM bt_evidence_items ei
                   ORDER BY ei.relevance_score DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        except Exception as e:
            logger.warning("Cannot query bt_evidence_items: %s", e)
            rows = []

        for row in rows:
            try:
                self._ingest_evidence_item(row, domain)
                stats["ingested"] += 1
            except Exception as e:
                stats["errors"] += 1

        return stats

    def _ingest_paper_row(self, row: sqlite3.Row, domain: str) -> None:
        """Ingest a single paper row into bt_paper_segments."""
        paper_id = row[0]
        title = row[1] or ""
        arxiv_id = row[2] or ""
        doi = row[3] or ""
        content = row[4] or ""
        provenance = row[5] or ""

        source_id = f"arxiv:{arxiv_id}" if arxiv_id else (f"doi:{doi}" if doi else f"paper:{paper_id}")

        # Build text: title + provenance + content
        full_text = f"{title}. {provenance} {content}".strip()
        segments = segment_text(full_text, self.config.segment_max_chars)

        if not segments:
            segments = [full_text[:self.config.segment_max_chars]]

        # Score relevance
        scores = (
            self._scorer.score_batch([s for s in segments], domain)
            if self._scorer
            else [0.5] * len(segments)
        )

        for idx, (seg_text, score) in enumerate(zip(segments, scores)):
            if score < self.config.min_relevance:
                continue

            compressed = ""
            if self.config.compress and len(seg_text) > 500:
                compressed = compress_segment(
                    seg_text,
                    host=self.config.ollama_host,
                    model=self.config.ollama_model,
                    timeout=self.config.ollama_timeout,
                )

            seg = {
                "id": new_id(),
                "paper_id": paper_id,
                "source_id": source_id,
                "segment_index": idx,
                "raw_text": seg_text[:10000],
                "compressed_text": compressed[:5000] if compressed else "",
                "relevance_score": round(score, 4),
                "domain": domain,
                "status": "scored" if self._scorer else "ingested",
            }
            self.repo.save_paper_segment(seg)

    def _ingest_evidence_item(self, row: sqlite3.Row, domain: str) -> None:
        """Ingest from a bt_evidence_items row."""
        eid = row[0]
        source_id = row[1] or ""
        title = row[2] or ""
        quote = row[3] or ""

        full_text = f"{title}. {quote}".strip()
        if not full_text or len(full_text) < 20:
            return

        score = 0.5
        if self._scorer:
            score = self._scorer.score(full_text, domain)
            if score < self.config.min_relevance:
                return

        seg = {
            "id": new_id(),
            "paper_id": eid,
            "source_id": source_id,
            "segment_index": 0,
            "raw_text": full_text[:10000],
            "compressed_text": "",
            "relevance_score": round(score, 4),
            "domain": domain,
            "status": "scored" if self._scorer else "ingested",
        }
        self.repo.save_paper_segment(seg)
