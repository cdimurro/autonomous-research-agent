"""Shadow retrieval comparison harness.

Phase 10A: Runs the current production retrieval and KG shadow retrieval
side by side for the same domain/profile, comparing evidence quality,
diversity, and relevance.

This is the primary safety guard — KG retrieval must demonstrably outperform
current retrieval before any production switch.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .evidence_source import EvidenceSource
from .models import EvidenceItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Comparison result models
# ---------------------------------------------------------------------------

@dataclass
class SourceMetrics:
    """Metrics for a single retrieval source."""
    source_name: str = ""
    item_count: int = 0
    mean_relevance: float = 0.0
    max_relevance: float = 0.0
    min_relevance: float = 0.0
    source_type_counts: dict = field(default_factory=dict)
    unique_source_ids: int = 0
    mean_quote_length: float = 0.0

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "item_count": self.item_count,
            "mean_relevance": round(self.mean_relevance, 4),
            "max_relevance": round(self.max_relevance, 4),
            "min_relevance": round(self.min_relevance, 4),
            "source_type_counts": self.source_type_counts,
            "unique_source_ids": self.unique_source_ids,
            "mean_quote_length": round(self.mean_quote_length, 1),
        }


@dataclass
class ComparisonResult:
    """Result of comparing two or three retrieval sources."""
    domain: str = ""
    limit: int = 20
    current_metrics: Optional[SourceMetrics] = None
    shadow_metrics: Optional[SourceMetrics] = None
    hybrid_metrics: Optional[SourceMetrics] = None
    overlap_count: int = 0
    overlap_source_ids: list[str] = field(default_factory=list)
    verdict: str = "inconclusive"
    hybrid_verdict: str = "not_tested"
    notes: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        d = {
            "domain": self.domain,
            "limit": self.limit,
            "current": self.current_metrics.to_dict() if self.current_metrics else {},
            "shadow": self.shadow_metrics.to_dict() if self.shadow_metrics else {},
            "overlap_count": self.overlap_count,
            "overlap_source_ids": self.overlap_source_ids[:20],
            "verdict": self.verdict,
            "hybrid_verdict": self.hybrid_verdict,
            "notes": self.notes,
            "timestamp": self.timestamp,
        }
        if self.hybrid_metrics:
            d["hybrid"] = self.hybrid_metrics.to_dict()
        return d


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def _compute_metrics(items: list[EvidenceItem], name: str) -> SourceMetrics:
    """Compute metrics for a list of evidence items."""
    if not items:
        return SourceMetrics(source_name=name)

    relevances = [it.relevance_score for it in items]
    source_types: dict[str, int] = {}
    source_ids: set[str] = set()
    quote_lengths: list[int] = []

    for it in items:
        source_types[it.source_type] = source_types.get(it.source_type, 0) + 1
        source_ids.add(it.source_id)
        quote_lengths.append(len(it.quote))

    return SourceMetrics(
        source_name=name,
        item_count=len(items),
        mean_relevance=sum(relevances) / len(relevances),
        max_relevance=max(relevances),
        min_relevance=min(relevances),
        source_type_counts=source_types,
        unique_source_ids=len(source_ids),
        mean_quote_length=sum(quote_lengths) / len(quote_lengths) if quote_lengths else 0,
    )


def _compute_overlap(
    current: list[EvidenceItem], shadow: list[EvidenceItem],
) -> tuple[int, list[str]]:
    """Compute source_id overlap between two evidence sets."""
    current_ids = {it.source_id for it in current}
    shadow_ids = {it.source_id for it in shadow}
    overlap = current_ids & shadow_ids
    return len(overlap), sorted(overlap)[:20]


def _verdict(current: SourceMetrics, shadow: SourceMetrics) -> tuple[str, list[str]]:
    """Determine comparison verdict."""
    notes: list[str] = []

    if shadow.item_count == 0:
        return "shadow_empty", ["KG retrieval returned no items"]

    if current.item_count == 0:
        return "current_empty", ["Current retrieval returned no items"]

    # Compare mean relevance
    rel_diff = shadow.mean_relevance - current.mean_relevance
    if rel_diff > 0.05:
        notes.append(f"Shadow mean relevance higher by {rel_diff:.3f}")
    elif rel_diff < -0.05:
        notes.append(f"Shadow mean relevance lower by {abs(rel_diff):.3f}")

    # Compare diversity
    div_diff = shadow.unique_source_ids - current.unique_source_ids
    if div_diff > 2:
        notes.append(f"Shadow has {div_diff} more unique sources")
    elif div_diff < -2:
        notes.append(f"Shadow has {abs(div_diff)} fewer unique sources")

    # Compare item count
    if shadow.item_count < current.item_count * 0.5:
        notes.append("Shadow returned significantly fewer items")

    # Determine verdict
    shadow_wins = 0
    current_wins = 0

    if shadow.mean_relevance > current.mean_relevance + 0.02:
        shadow_wins += 1
    elif current.mean_relevance > shadow.mean_relevance + 0.02:
        current_wins += 1

    if shadow.unique_source_ids > current.unique_source_ids:
        shadow_wins += 1
    elif current.unique_source_ids > shadow.unique_source_ids:
        current_wins += 1

    if shadow.item_count >= current.item_count:
        shadow_wins += 1
    elif current.item_count > shadow.item_count:
        current_wins += 1

    if shadow_wins > current_wins:
        verdict = "shadow_better"
    elif current_wins > shadow_wins:
        verdict = "current_better"
    else:
        verdict = "comparable"

    return verdict, notes


# ---------------------------------------------------------------------------
# Comparison harness
# ---------------------------------------------------------------------------

class RetrievalComparisonHarness:
    """Runs current vs KG shadow retrieval side by side.

    Phase 10D: supports optional third source (hybrid) for 3-way comparison.

    Usage:
        harness = RetrievalComparisonHarness(current_source, shadow_source, hybrid_source)
        result = harness.compare(domain="clean-energy", limit=20)
        harness.export_json(result, "comparison_output.json")
    """

    def __init__(
        self,
        current_source: EvidenceSource,
        shadow_source: EvidenceSource,
        hybrid_source: Optional[EvidenceSource] = None,
    ):
        self.current_source = current_source
        self.shadow_source = shadow_source
        self.hybrid_source = hybrid_source

    def compare(self, domain: str, limit: int = 20) -> ComparisonResult:
        """Run all sources and compare results."""
        result = ComparisonResult(
            domain=domain,
            limit=limit,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        # Gather from all sources
        try:
            current_items = self.current_source.gather(domain, limit=limit)
        except Exception as e:
            logger.warning("Current source failed: %s", e)
            current_items = []
            result.notes.append(f"Current source error: {e}")

        try:
            shadow_items = self.shadow_source.gather(domain, limit=limit)
        except Exception as e:
            logger.warning("Shadow source failed: %s", e)
            shadow_items = []
            result.notes.append(f"Shadow source error: {e}")

        hybrid_items: list[EvidenceItem] = []
        if self.hybrid_source:
            try:
                hybrid_items = self.hybrid_source.gather(domain, limit=limit)
            except Exception as e:
                logger.warning("Hybrid source failed: %s", e)
                result.notes.append(f"Hybrid source error: {e}")

        # Compute metrics
        result.current_metrics = _compute_metrics(current_items, "current")
        result.shadow_metrics = _compute_metrics(shadow_items, "kg_shadow")
        if hybrid_items:
            result.hybrid_metrics = _compute_metrics(hybrid_items, "hybrid")

        # Compute overlap (current vs shadow)
        result.overlap_count, result.overlap_source_ids = _compute_overlap(
            current_items, shadow_items,
        )

        # Determine verdicts
        result.verdict, verdict_notes = _verdict(
            result.current_metrics, result.shadow_metrics,
        )
        result.notes.extend(verdict_notes)

        if result.hybrid_metrics and result.current_metrics:
            result.hybrid_verdict, hybrid_notes = _verdict(
                result.current_metrics, result.hybrid_metrics,
            )
            result.notes.extend([f"[hybrid] {n}" for n in hybrid_notes])

        logger.info(
            "RetrievalComparison: domain=%s current=%d shadow=%d hybrid=%d "
            "overlap=%d verdict=%s hybrid_verdict=%s",
            domain, len(current_items), len(shadow_items), len(hybrid_items),
            result.overlap_count, result.verdict, result.hybrid_verdict,
        )

        return result

    @staticmethod
    def export_json(result: ComparisonResult, path: str) -> None:
        """Export comparison result as JSON."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info("Comparison exported to %s", path)

    @staticmethod
    def export_markdown(result: ComparisonResult, path: str) -> None:
        """Export comparison result as Markdown."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        d = result.to_dict()
        lines = [
            f"# Retrieval Comparison: {result.domain}",
            f"",
            f"**Timestamp:** {result.timestamp}",
            f"**Verdict:** {result.verdict}",
            f"**Limit:** {result.limit}",
            f"",
            f"## Current Retrieval",
            f"- Items: {d['current'].get('item_count', 0)}",
            f"- Mean relevance: {d['current'].get('mean_relevance', 0):.4f}",
            f"- Unique sources: {d['current'].get('unique_source_ids', 0)}",
            f"- Source types: {d['current'].get('source_type_counts', {})}",
            f"",
            f"## KG Shadow Retrieval",
            f"- Items: {d['shadow'].get('item_count', 0)}",
            f"- Mean relevance: {d['shadow'].get('mean_relevance', 0):.4f}",
            f"- Unique sources: {d['shadow'].get('unique_source_ids', 0)}",
            f"- Source types: {d['shadow'].get('source_type_counts', {})}",
            f"",
            f"## Overlap",
            f"- Shared source IDs: {result.overlap_count}",
            f"",
            f"## Notes",
        ]
        for note in result.notes:
            lines.append(f"- {note}")

        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        logger.info("Comparison markdown exported to %s", path)

    @staticmethod
    def export_csv(result: ComparisonResult, path: str) -> None:
        """Export comparison summary as CSV."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        import csv
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "source", "item_count", "mean_relevance", "max_relevance",
                "min_relevance", "unique_source_ids", "mean_quote_length",
            ])
            for metrics in [result.current_metrics, result.shadow_metrics]:
                if metrics:
                    writer.writerow([
                        metrics.source_name, metrics.item_count,
                        round(metrics.mean_relevance, 4),
                        round(metrics.max_relevance, 4),
                        round(metrics.min_relevance, 4),
                        metrics.unique_source_ids,
                        round(metrics.mean_quote_length, 1),
                    ])
        logger.info("Comparison CSV exported to %s", path)
