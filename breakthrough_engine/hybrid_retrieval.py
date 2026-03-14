"""Hybrid retrieval source combining trusted findings + KG diversification.

Phase 10D: Does NOT replace production retrieval. Provides a composite
evidence source that preserves trusted anchors while adding KG-backed
diversity evidence. Shadow-only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .evidence_source import EvidenceSource
from .kg_calibration import EvidenceCalibrator
from .models import EvidenceItem

logger = logging.getLogger(__name__)


@dataclass
class HybridMixDiagnostics:
    """Diagnostics for a hybrid evidence mix."""
    total_items: int = 0
    trusted_items: int = 0
    kg_items: int = 0
    deduplicated: int = 0
    trusted_source_types: dict[str, int] = field(default_factory=dict)
    kg_source_types: dict[str, int] = field(default_factory=dict)
    unique_source_ids: int = 0
    top1_concentration: float = 0.0
    calibration_applied: bool = False

    def to_dict(self) -> dict:
        return {
            "total_items": self.total_items,
            "trusted_items": self.trusted_items,
            "kg_items": self.kg_items,
            "deduplicated": self.deduplicated,
            "trusted_source_types": self.trusted_source_types,
            "kg_source_types": self.kg_source_types,
            "unique_source_ids": self.unique_source_ids,
            "top1_concentration": round(self.top1_concentration, 3),
            "calibration_applied": self.calibration_applied,
        }


class HybridKGEvidenceSource(EvidenceSource):
    """Combines trusted production findings with KG diversification evidence.

    Controls:
    - min_trusted_quota: minimum number of trusted finding items to include
    - max_single_source_pct: cap on any single source_id's share of total items
    - kg_diversification_quota: maximum KG items to add for diversity
    - calibrate: whether to apply source-aware calibration to KG items

    The hybrid source preserves the strongest current signals while
    reducing evidence monoculture.
    """

    def __init__(
        self,
        trusted_source: EvidenceSource,
        kg_source: EvidenceSource,
        min_trusted_quota: int = 10,
        max_single_source_pct: float = 0.50,
        kg_diversification_quota: int = 10,
        calibrator: Optional[EvidenceCalibrator] = None,
        min_kg_items: int = 2,
        max_per_paper: int = 3,
    ):
        self.trusted_source = trusted_source
        self.kg_source = kg_source
        self.min_trusted_quota = min_trusted_quota
        self.max_single_source_pct = max_single_source_pct
        self.kg_diversification_quota = kg_diversification_quota
        self.calibrator = calibrator or EvidenceCalibrator()
        self.min_kg_items = min_kg_items
        self.max_per_paper = max_per_paper
        self._last_diagnostics: Optional[HybridMixDiagnostics] = None

    @property
    def last_diagnostics(self) -> Optional[HybridMixDiagnostics]:
        return self._last_diagnostics

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        """Gather hybrid evidence: trusted anchors + KG diversification.

        Phase 10J: Source-aware pool construction guarantees KG items in the
        pool and caps per-paper concentration. Previously KG items were trimmed
        because their calibrated relevance was below trusted findings, and the
        pure relevance sort excluded them entirely.
        """
        diag = HybridMixDiagnostics()

        # 1. Get trusted items (production findings)
        trusted_limit = max(self.min_trusted_quota, limit)
        trusted_items = self.trusted_source.gather(domain, limit=trusted_limit)

        # 2. Get KG items
        kg_limit = max(self.kg_diversification_quota, limit)
        kg_items = self.kg_source.gather(domain, limit=kg_limit)

        # 3. Calibrate KG items
        if kg_items:
            self.calibrator.calibrate(kg_items)
            diag.calibration_applied = True

        # 4. Phase 10J: Apply per-paper cap to trusted items to prevent
        # any single paper from dominating the pool
        trusted_capped = self._cap_per_paper(trusted_items)

        # 5. Deduplicate KG items against trusted source_ids
        trusted_source_ids = {it.source_id for it in trusted_capped}
        kg_deduped = [it for it in kg_items if it.source_id not in trusted_source_ids]
        dedup_count = len(kg_items) - len(kg_deduped)

        # 6. Phase 10J: Source-aware pool construction
        # Reserve slots for KG items to guarantee they're not all excluded
        # by pure relevance sorting
        kg_reserved = min(self.min_kg_items, len(kg_deduped))
        trusted_slots = limit - kg_reserved
        trusted_take = trusted_capped[:trusted_slots]

        # Select KG items: prefer items from diverse sources
        kg_take = self._select_diverse_kg(kg_deduped, kg_reserved)

        # 7. Combine: trusted first (by relevance), then reserved KG
        combined = trusted_take + kg_take
        # Fill remaining slots from any leftover items if under limit
        if len(combined) < limit:
            used_ids = {it.id for it in combined}
            remaining = [it for it in trusted_capped + kg_deduped
                         if it.id not in used_ids]
            remaining.sort(key=lambda x: x.relevance_score, reverse=True)
            combined.extend(remaining[:limit - len(combined)])

        # Sort final pool by relevance for downstream ranking
        combined.sort(key=lambda x: x.relevance_score, reverse=True)
        result = combined[:limit]

        # 8. Build diagnostics
        diag.total_items = len(result)
        diag.trusted_items = sum(1 for it in result if it.source_type in ("finding", "paper"))
        diag.kg_items = sum(1 for it in result if it.source_type in ("kg_segment", "kg_graph"))
        diag.deduplicated = dedup_count

        for it in result:
            if it.source_type in ("finding", "paper"):
                diag.trusted_source_types[it.source_type] = diag.trusted_source_types.get(it.source_type, 0) + 1
            else:
                diag.kg_source_types[it.source_type] = diag.kg_source_types.get(it.source_type, 0) + 1

        source_id_counts: dict[str, int] = {}
        for it in result:
            source_id_counts[it.source_id] = source_id_counts.get(it.source_id, 0) + 1
        diag.unique_source_ids = len(source_id_counts)
        if result:
            diag.top1_concentration = max(source_id_counts.values()) / len(result)

        self._last_diagnostics = diag

        logger.info(
            "HybridKGEvidenceSource: domain=%s trusted=%d kg=%d dedup=%d total=%d "
            "unique_sources=%d top1_conc=%.2f",
            domain, diag.trusted_items, diag.kg_items, dedup_count,
            len(result), diag.unique_source_ids, diag.top1_concentration,
        )
        return result

    def _cap_per_paper(self, items: list[EvidenceItem]) -> list[EvidenceItem]:
        """Cap items per paper/source_id to max_per_paper."""
        source_counts: dict[str, int] = {}
        result: list[EvidenceItem] = []
        for it in items:
            cnt = source_counts.get(it.source_id, 0)
            if cnt < self.max_per_paper:
                result.append(it)
                source_counts[it.source_id] = cnt + 1
        return result

    def _select_diverse_kg(
        self, kg_items: list[EvidenceItem], k: int,
    ) -> list[EvidenceItem]:
        """Select k KG items preferring items from distinct sources."""
        if not kg_items or k <= 0:
            return []
        selected: list[EvidenceItem] = []
        seen_sources: set[str] = set()
        # First pass: one item per source
        for it in kg_items:
            if len(selected) >= k:
                break
            if it.source_id not in seen_sources:
                selected.append(it)
                seen_sources.add(it.source_id)
        # Second pass: fill remaining from any source
        if len(selected) < k:
            selected_ids = {it.id for it in selected}
            for it in kg_items:
                if len(selected) >= k:
                    break
                if it.id not in selected_ids:
                    selected.append(it)
        return selected

