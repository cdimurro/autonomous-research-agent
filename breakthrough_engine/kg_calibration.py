"""Source-aware score calibration for KG evidence.

Phase 10D: Calibrates KG segment/graph relevance scores to be comparable
with production finding scores. Uses distribution-based normalization
so that KG evidence competes fairly in ranking and scoring.

Calibration is explainable: raw scores preserved, calibrated scores logged.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from .models import EvidenceItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Calibration profiles — observed distributions from Phase 10C
# ---------------------------------------------------------------------------

@dataclass
class SourceCalibrationProfile:
    """Observed score distribution for a source type."""
    source_type: str
    observed_mean: float
    observed_std: float
    observed_min: float
    observed_max: float
    target_mean: float
    target_std: float
    target_min: float
    target_max: float

    def calibrate(self, raw_score: float) -> float:
        """Map raw score to calibrated score via linear rescaling.

        Preserves relative ordering within source type while mapping
        to the target distribution range.
        """
        if self.observed_max <= self.observed_min:
            return self.target_mean

        # Normalize to [0, 1] within observed range
        t = (raw_score - self.observed_min) / (self.observed_max - self.observed_min)
        t = max(0.0, min(1.0, t))

        # Map to target range
        calibrated = self.target_min + t * (self.target_max - self.target_min)
        return round(calibrated, 4)


# Default profiles based on Phase 10C observations:
#   KG segments: mean=0.584, range=[0.322, 0.602]
#   Findings:    mean=0.874, range=[0.810, 0.930]
# Target: map KG segment scores to overlap the lower-mid range of findings
# so they compete but don't blindly match top findings.

DEFAULT_PROFILES: dict[str, SourceCalibrationProfile] = {
    "kg_segment": SourceCalibrationProfile(
        source_type="kg_segment",
        observed_mean=0.584, observed_std=0.06,
        observed_min=0.322, observed_max=0.602,
        target_mean=0.82, target_std=0.05,
        target_min=0.75, target_max=0.88,
    ),
    "kg_graph": SourceCalibrationProfile(
        source_type="kg_graph",
        observed_mean=0.50, observed_std=0.10,
        observed_min=0.30, observed_max=0.70,
        target_mean=0.78, target_std=0.06,
        target_min=0.70, target_max=0.85,
    ),
    "finding": SourceCalibrationProfile(
        source_type="finding",
        observed_mean=0.874, observed_std=0.03,
        observed_min=0.810, observed_max=0.930,
        # Identity mapping — findings are already on the target scale
        target_mean=0.874, target_std=0.03,
        target_min=0.810, target_max=0.930,
    ),
    "paper": SourceCalibrationProfile(
        source_type="paper",
        observed_mean=0.85, observed_std=0.05,
        observed_min=0.70, observed_max=0.95,
        target_mean=0.85, target_std=0.05,
        target_min=0.70, target_max=0.95,
    ),
}


# ---------------------------------------------------------------------------
# Calibration engine
# ---------------------------------------------------------------------------

@dataclass
class CalibrationResult:
    """Result of calibrating evidence items."""
    items: list[EvidenceItem] = field(default_factory=list)
    raw_scores: dict[str, float] = field(default_factory=dict)  # item.id -> raw
    calibrated_scores: dict[str, float] = field(default_factory=dict)  # item.id -> calibrated
    source_type_stats: dict[str, dict] = field(default_factory=dict)
    profiles_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        stats = {}
        for st, s in self.source_type_stats.items():
            stats[st] = s
        return {
            "item_count": len(self.items),
            "profiles_used": self.profiles_used,
            "source_type_stats": stats,
            "sample_calibrations": [
                {"id": item.id[:8], "source_type": item.source_type,
                 "raw": self.raw_scores.get(item.id, 0),
                 "calibrated": self.calibrated_scores.get(item.id, 0)}
                for item in self.items[:10]
            ],
        }


class EvidenceCalibrator:
    """Calibrates evidence relevance scores by source type.

    Preserves raw scores, applies calibrated scores to items,
    and logs all transformations for auditability.
    """

    def __init__(
        self,
        profiles: Optional[dict[str, SourceCalibrationProfile]] = None,
    ):
        self.profiles = profiles or dict(DEFAULT_PROFILES)

    def calibrate(self, items: list[EvidenceItem]) -> CalibrationResult:
        """Calibrate a list of evidence items in-place.

        Returns CalibrationResult with raw/calibrated score mappings.
        Items whose source_type has no profile are left unchanged.
        """
        result = CalibrationResult(items=items)
        type_raws: dict[str, list[float]] = {}
        type_cals: dict[str, list[float]] = {}

        for item in items:
            raw = item.relevance_score
            result.raw_scores[item.id] = raw

            profile = self.profiles.get(item.source_type)
            if profile:
                calibrated = profile.calibrate(raw)
                if profile.source_type not in result.profiles_used:
                    result.profiles_used.append(profile.source_type)
            else:
                calibrated = raw  # no profile = identity

            item.relevance_score = calibrated
            result.calibrated_scores[item.id] = calibrated

            type_raws.setdefault(item.source_type, []).append(raw)
            type_cals.setdefault(item.source_type, []).append(calibrated)

        # Compute per-type stats
        for st in type_raws:
            raws = type_raws[st]
            cals = type_cals[st]
            result.source_type_stats[st] = {
                "count": len(raws),
                "raw_mean": round(sum(raws) / len(raws), 4),
                "raw_min": round(min(raws), 4),
                "raw_max": round(max(raws), 4),
                "calibrated_mean": round(sum(cals) / len(cals), 4),
                "calibrated_min": round(min(cals), 4),
                "calibrated_max": round(max(cals), 4),
            }

        logger.info(
            "EvidenceCalibrator: calibrated %d items across %d source types: %s",
            len(items), len(type_raws), list(type_raws.keys()),
        )
        return result

    def get_profile(self, source_type: str) -> Optional[SourceCalibrationProfile]:
        return self.profiles.get(source_type)

    def set_profile(self, profile: SourceCalibrationProfile) -> None:
        self.profiles[profile.source_type] = profile
