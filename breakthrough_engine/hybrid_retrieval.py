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
    ):
        self.trusted_source = trusted_source
        self.kg_source = kg_source
        self.min_trusted_quota = min_trusted_quota
        self.max_single_source_pct = max_single_source_pct
        self.kg_diversification_quota = kg_diversification_quota
        self.calibrator = calibrator or EvidenceCalibrator()
        self._last_diagnostics: Optional[HybridMixDiagnostics] = None

    @property
    def last_diagnostics(self) -> Optional[HybridMixDiagnostics]:
        return self._last_diagnostics

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        """Gather hybrid evidence: trusted anchors + KG diversification."""
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

        # 4. Enforce single-source concentration cap on trusted items
        trusted_capped = self._cap_single_source(trusted_items, limit)

        # 5. Take at least min_trusted_quota from trusted
        trusted_take = trusted_capped[:max(self.min_trusted_quota, limit - self.kg_diversification_quota)]

        # 6. Deduplicate KG items against trusted source_ids
        trusted_source_ids = {it.source_id for it in trusted_take}
        kg_deduped = [it for it in kg_items if it.source_id not in trusted_source_ids]
        dedup_count = len(kg_items) - len(kg_deduped)

        # 7. Take KG diversification quota
        kg_take = kg_deduped[:self.kg_diversification_quota]

        # 8. Combine and sort by relevance
        combined = trusted_take + kg_take
        combined.sort(key=lambda x: x.relevance_score, reverse=True)
        result = combined[:limit]

        # 9. Build diagnostics
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

    def _cap_single_source(
        self, items: list[EvidenceItem], total_limit: int,
    ) -> list[EvidenceItem]:
        """Cap any single source_id to max_single_source_pct of total_limit."""
        max_per_source = max(1, int(total_limit * self.max_single_source_pct))
        source_counts: dict[str, int] = {}
        result: list[EvidenceItem] = []

        for it in items:
            cnt = source_counts.get(it.source_id, 0)
            if cnt < max_per_source:
                result.append(it)
                source_counts[it.source_id] = cnt + 1

        return result
