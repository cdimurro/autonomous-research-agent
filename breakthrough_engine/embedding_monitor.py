"""Embedding observability and drift monitoring for the Breakthrough Engine.

Tracks per-run embedding novelty statistics and provides
cross-run drift analysis. Phase 4C addition.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from .db import Repository
from .embeddings import EmbeddingNoveltyDetail, EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass
class RunEmbeddingStats:
    """Per-run embedding novelty statistics."""
    run_id: str
    embedding_model: str = "mock"
    embedding_dim: int = 64
    similarity_threshold: float = 0.88
    warn_threshold: float = 0.78
    candidates_evaluated: int = 0
    blocked_count: int = 0
    warned_count: int = 0
    max_similarity: float = 0.0
    mean_similarity: float = 0.0
    top_k_similarities: list[float] = field(default_factory=list)
    nearest_neighbor_summary: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "similarity_threshold": self.similarity_threshold,
            "warn_threshold": self.warn_threshold,
            "candidates_evaluated": self.candidates_evaluated,
            "blocked_count": self.blocked_count,
            "warned_count": self.warned_count,
            "max_similarity": round(self.max_similarity, 4),
            "mean_similarity": round(self.mean_similarity, 4),
            "top_k_similarities": [round(s, 4) for s in self.top_k_similarities[:10]],
            "nearest_neighbor_summary": self.nearest_neighbor_summary[:10],
        }


class EmbeddingMonitor:
    """Collects and analyzes embedding novelty metrics across runs."""

    def __init__(self, repo: Repository):
        self.repo = repo
        self._current_stats: Optional[RunEmbeddingStats] = None

    def start_run(
        self,
        run_id: str,
        provider: EmbeddingProvider,
        similarity_threshold: float = 0.88,
        warn_threshold: float = 0.78,
    ) -> None:
        """Initialize monitoring for a new run."""
        model_name = "mock"
        if hasattr(provider, "model"):
            model_name = provider.model
        elif type(provider).__name__ == "MockEmbeddingProvider":
            model_name = "mock"

        self._current_stats = RunEmbeddingStats(
            run_id=run_id,
            embedding_model=model_name,
            embedding_dim=provider.dimension(),
            similarity_threshold=similarity_threshold,
            warn_threshold=warn_threshold,
        )

    def record_evaluation(self, detail: EmbeddingNoveltyDetail) -> None:
        """Record a single candidate's embedding novelty result."""
        if not self._current_stats:
            return

        self._current_stats.candidates_evaluated += 1

        if detail.blocked_by_prior_art:
            self._current_stats.blocked_count += 1

        if detail.embedding_similarity_max >= self._current_stats.warn_threshold:
            if not detail.blocked_by_prior_art:
                self._current_stats.warned_count += 1

        if detail.embedding_similarity_max > self._current_stats.max_similarity:
            self._current_stats.max_similarity = detail.embedding_similarity_max

        self._current_stats.top_k_similarities.append(detail.embedding_similarity_max)
        self._current_stats.top_k_similarities.sort(reverse=True)
        self._current_stats.top_k_similarities = self._current_stats.top_k_similarities[:10]

        for nn in detail.nearest_neighbors[:3]:
            self._current_stats.nearest_neighbor_summary.append(nn)
        # Deduplicate by title, keep top entries
        seen = set()
        deduped = []
        for nn in sorted(self._current_stats.nearest_neighbor_summary,
                         key=lambda x: x.get("similarity", 0), reverse=True):
            key = nn.get("title", "")[:50]
            if key not in seen:
                seen.add(key)
                deduped.append(nn)
        self._current_stats.nearest_neighbor_summary = deduped[:10]

    def finish_run(self) -> Optional[RunEmbeddingStats]:
        """Finalize and persist the run's embedding stats."""
        if not self._current_stats:
            return None

        stats = self._current_stats
        if stats.top_k_similarities:
            stats.mean_similarity = sum(stats.top_k_similarities) / len(stats.top_k_similarities)

        try:
            self.repo.save_embedding_monitor(stats.to_dict())
        except Exception as e:
            logger.warning("Failed to save embedding monitor: %s", e)

        self._current_stats = None
        return stats

    def get_drift_report(self, limit: int = 10) -> dict:
        """Analyze embedding drift across recent runs.

        Returns a report showing:
        - Similarity distribution trends
        - Block/warn rate trends
        - Repeated nearest-neighbor clusters
        """
        monitors = self.repo.list_embedding_monitors(limit=limit)
        if not monitors:
            return {"status": "no_data", "runs_analyzed": 0}

        report: dict = {
            "status": "ok",
            "runs_analyzed": len(monitors),
            "trend": [],
            "repeated_neighbors": [],
            "summary": {},
        }

        all_max_sims = []
        all_mean_sims = []
        block_rates = []
        neighbor_titles: dict[str, int] = {}

        for m in monitors:
            max_sim = m.get("max_similarity", 0.0)
            mean_sim = m.get("mean_similarity", 0.0)
            evaluated = m.get("candidates_evaluated", 0)
            blocked = m.get("blocked_count", 0)

            all_max_sims.append(max_sim)
            all_mean_sims.append(mean_sim)
            block_rate = blocked / max(1, evaluated)
            block_rates.append(block_rate)

            report["trend"].append({
                "run_id": m.get("run_id", "")[:12],
                "model": m.get("embedding_model", "?"),
                "max_sim": round(max_sim, 4),
                "mean_sim": round(mean_sim, 4),
                "evaluated": evaluated,
                "blocked": blocked,
                "warned": m.get("warned_count", 0),
                "block_rate": round(block_rate, 3),
            })

            # Track repeated neighbors
            nn_raw = m.get("nearest_neighbor_summary", "[]")
            if isinstance(nn_raw, str):
                try:
                    nns = json.loads(nn_raw)
                except (json.JSONDecodeError, TypeError):
                    nns = []
            else:
                nns = nn_raw or []
            for nn in nns:
                title = nn.get("title", "")[:60]
                if title:
                    neighbor_titles[title] = neighbor_titles.get(title, 0) + 1

        # Summary stats
        report["summary"] = {
            "avg_max_similarity": round(sum(all_max_sims) / len(all_max_sims), 4) if all_max_sims else 0,
            "avg_mean_similarity": round(sum(all_mean_sims) / len(all_mean_sims), 4) if all_mean_sims else 0,
            "avg_block_rate": round(sum(block_rates) / len(block_rates), 3) if block_rates else 0,
            "total_blocked": sum(m.get("blocked_count", 0) for m in monitors),
            "total_warned": sum(m.get("warned_count", 0) for m in monitors),
            "total_evaluated": sum(m.get("candidates_evaluated", 0) for m in monitors),
        }

        # Saturation check: are similarities trending upward?
        if len(all_max_sims) >= 3:
            recent_avg = sum(all_max_sims[:3]) / 3
            older_avg = sum(all_max_sims[-3:]) / min(3, len(all_max_sims[-3:]))
            if recent_avg > older_avg + 0.05:
                report["summary"]["saturation_warning"] = (
                    f"Recent max similarity ({recent_avg:.3f}) is trending higher than older runs ({older_avg:.3f}). "
                    "Novelty space may be saturating."
                )

        # Repeated neighbors (appears in 2+ runs)
        report["repeated_neighbors"] = [
            {"title": t, "appearances": c}
            for t, c in sorted(neighbor_titles.items(), key=lambda x: -x[1])
            if c >= 2
        ][:10]

        return report
