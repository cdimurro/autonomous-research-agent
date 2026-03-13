"""Phase 10D: KG Hardening — offline-safe tests.

Tests cover:
- Source-aware calibration behavior
- Source-type-aware ranking behavior
- Hybrid retrieval source composition
- 3-way comparison harness
- Switch-readiness decision logic
"""

from __future__ import annotations

import json

import pytest

from breakthrough_engine.evidence_source import EvidenceSource
from breakthrough_engine.hybrid_retrieval import HybridKGEvidenceSource, HybridMixDiagnostics
from breakthrough_engine.kg_calibration import (
    DEFAULT_PROFILES,
    CalibrationResult,
    EvidenceCalibrator,
    SourceCalibrationProfile,
)
from breakthrough_engine.kg_comparison import (
    ComparisonResult,
    RetrievalComparisonHarness,
    SourceMetrics,
    _compute_metrics,
)
from breakthrough_engine.models import EvidenceItem, new_id
from breakthrough_engine.retrieval import rank_evidence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(source_type: str, relevance: float, source_id: str = "") -> EvidenceItem:
    return EvidenceItem(
        id=new_id(),
        source_type=source_type,
        source_id=source_id or f"test:{source_type}:{relevance}",
        title=f"Test {source_type} item",
        quote=f"This is a test quote for {source_type} evidence with relevance {relevance}.",
        citation=f"Test citation 2024",
        relevance_score=relevance,
    )


class MockSource(EvidenceSource):
    def __init__(self, items: list[EvidenceItem]):
        self._items = items

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        return self._items[:limit]


# ===========================================================================
# A. Calibration Tests
# ===========================================================================

class TestSourceCalibrationProfile:
    def test_calibrate_maps_to_target_range(self):
        p = SourceCalibrationProfile(
            source_type="kg_segment",
            observed_mean=0.5, observed_std=0.1,
            observed_min=0.3, observed_max=0.6,
            target_mean=0.8, target_std=0.05,
            target_min=0.7, target_max=0.9,
        )
        # Min maps to target_min
        assert p.calibrate(0.3) == 0.7
        # Max maps to target_max
        assert p.calibrate(0.6) == 0.9
        # Mid maps to mid
        assert abs(p.calibrate(0.45) - 0.8) < 0.01

    def test_calibrate_clamps_out_of_range(self):
        p = SourceCalibrationProfile(
            source_type="test",
            observed_mean=0.5, observed_std=0.1,
            observed_min=0.3, observed_max=0.7,
            target_mean=0.8, target_std=0.05,
            target_min=0.7, target_max=0.9,
        )
        # Below observed min clamps to target_min
        assert p.calibrate(0.1) == 0.7
        # Above observed max clamps to target_max
        assert p.calibrate(0.9) == 0.9

    def test_degenerate_range(self):
        p = SourceCalibrationProfile(
            source_type="test",
            observed_mean=0.5, observed_std=0.0,
            observed_min=0.5, observed_max=0.5,
            target_mean=0.8, target_std=0.0,
            target_min=0.7, target_max=0.9,
        )
        assert p.calibrate(0.5) == 0.8  # returns target_mean


class TestEvidenceCalibrator:
    def test_calibrate_changes_kg_scores(self):
        items = [
            _make_item("kg_segment", 0.5),
            _make_item("kg_segment", 0.6),
            _make_item("finding", 0.87),
        ]
        cal = EvidenceCalibrator()
        result = cal.calibrate(items)

        # KG items should be calibrated up
        for item in items:
            if item.source_type == "kg_segment":
                assert item.relevance_score > 0.6, f"Expected calibrated > 0.6, got {item.relevance_score}"
        # Finding should stay roughly the same (identity profile)
        assert items[2].relevance_score == pytest.approx(0.87, abs=0.05)

        assert "kg_segment" in result.profiles_used
        assert len(result.raw_scores) == 3
        assert len(result.calibrated_scores) == 3

    def test_calibrate_preserves_relative_order(self):
        items = [
            _make_item("kg_segment", 0.4),
            _make_item("kg_segment", 0.55),
            _make_item("kg_segment", 0.6),
        ]
        cal = EvidenceCalibrator()
        cal.calibrate(items)
        assert items[0].relevance_score < items[1].relevance_score < items[2].relevance_score

    def test_unknown_source_type_identity(self):
        items = [_make_item("alien_type", 0.42)]
        cal = EvidenceCalibrator()
        cal.calibrate(items)
        assert items[0].relevance_score == 0.42

    def test_result_to_dict(self):
        items = [_make_item("kg_segment", 0.5)]
        cal = EvidenceCalibrator()
        result = cal.calibrate(items)
        d = result.to_dict()
        assert "item_count" in d
        assert d["item_count"] == 1
        assert "profiles_used" in d

    def test_custom_profiles(self):
        p = SourceCalibrationProfile(
            source_type="custom",
            observed_mean=0.5, observed_std=0.1,
            observed_min=0.0, observed_max=1.0,
            target_mean=0.9, target_std=0.05,
            target_min=0.8, target_max=1.0,
        )
        cal = EvidenceCalibrator(profiles={"custom": p})
        items = [_make_item("custom", 0.5)]
        cal.calibrate(items)
        assert items[0].relevance_score == pytest.approx(0.9, abs=0.01)


# ===========================================================================
# B. Source-Type-Aware Ranking Tests
# ===========================================================================

class TestSourceTypeAwareRanking:
    def test_source_type_adjustment_applied(self):
        items = [
            _make_item("finding", 0.85),
            _make_item("kg_segment", 0.85),
        ]
        weights = {
            "api_relevance": 0.35,
            "domain_overlap": 0.30,
            "mechanism_overlap": 0.20,
            "baseline": 0.15,
            "source_type_adjustments": {
                "kg_segment": 0.05,
                "finding": 0.0,
            },
        }
        ranked = rank_evidence(items, domain="clean energy", evidence_ranking_weights=weights)
        assert len(ranked) == 2
        # KG segment should rank higher due to +0.05 adjustment
        assert ranked[0][0].source_type == "kg_segment"
        assert ranked[0][1]["source_type_adjustment"] == 0.05

    def test_no_adjustment_by_default(self):
        items = [_make_item("finding", 0.85)]
        ranked = rank_evidence(items, domain="clean energy")
        assert ranked[0][1]["source_type_adjustment"] == 0.0

    def test_mixed_source_types_ranked(self):
        items = [
            _make_item("finding", 0.90),
            _make_item("kg_segment", 0.80),
            _make_item("kg_graph", 0.70),
            _make_item("paper", 0.85),
        ]
        ranked = rank_evidence(items, domain="energy")
        assert len(ranked) == 4
        # All have source_type_adjustment in detail
        for _, detail in ranked:
            assert "source_type_adjustment" in detail


# ===========================================================================
# C. Hybrid Retrieval Tests
# ===========================================================================

class TestHybridKGEvidenceSource:
    def test_combines_trusted_and_kg(self):
        trusted = [_make_item("finding", 0.87, f"f:{i}") for i in range(5)]
        kg = [_make_item("kg_segment", 0.55, f"kg:{i}") for i in range(5)]
        source = HybridKGEvidenceSource(
            trusted_source=MockSource(trusted),
            kg_source=MockSource(kg),
            min_trusted_quota=3,
            kg_diversification_quota=3,
        )
        items = source.gather("clean energy", limit=6)
        assert len(items) == 6
        types = {it.source_type for it in items}
        assert "finding" in types
        assert "kg_segment" in types

    def test_deduplicates_by_source_id(self):
        shared_id = "shared:123"
        trusted = [_make_item("finding", 0.87, shared_id)]
        kg = [_make_item("kg_segment", 0.55, shared_id)]
        source = HybridKGEvidenceSource(
            trusted_source=MockSource(trusted),
            kg_source=MockSource(kg),
            min_trusted_quota=1,
            kg_diversification_quota=1,
        )
        items = source.gather("energy", limit=5)
        ids = [it.source_id for it in items]
        # shared_id should appear only once (from trusted)
        assert ids.count(shared_id) == 1

    def test_caps_single_source_concentration(self):
        # All trusted from same source
        trusted = [_make_item("finding", 0.87, "mono:1") for _ in range(20)]
        kg = [_make_item("kg_segment", 0.55, f"kg:{i}") for i in range(10)]
        source = HybridKGEvidenceSource(
            trusted_source=MockSource(trusted),
            kg_source=MockSource(kg),
            min_trusted_quota=5,
            max_single_source_pct=0.30,
            kg_diversification_quota=5,
        )
        items = source.gather("energy", limit=10)
        mono_count = sum(1 for it in items if it.source_id == "mono:1")
        assert mono_count <= 3  # 30% of 10

    def test_diagnostics_populated(self):
        trusted = [_make_item("finding", 0.87, f"f:{i}") for i in range(3)]
        kg = [_make_item("kg_segment", 0.55, f"kg:{i}") for i in range(3)]
        source = HybridKGEvidenceSource(
            trusted_source=MockSource(trusted),
            kg_source=MockSource(kg),
            min_trusted_quota=2,
            kg_diversification_quota=2,
        )
        source.gather("energy", limit=4)
        diag = source.last_diagnostics
        assert diag is not None
        assert diag.total_items == 4
        assert diag.unique_source_ids > 0
        d = diag.to_dict()
        assert "total_items" in d
        assert "top1_concentration" in d

    def test_calibration_applied_to_kg_items(self):
        trusted = [_make_item("finding", 0.87, "f:1")]
        kg = [_make_item("kg_segment", 0.50, "kg:1")]
        source = HybridKGEvidenceSource(
            trusted_source=MockSource(trusted),
            kg_source=MockSource(kg),
            min_trusted_quota=1,
            kg_diversification_quota=1,
        )
        items = source.gather("energy", limit=2)
        kg_item = next(it for it in items if it.source_type == "kg_segment")
        # Calibrated score should be higher than raw 0.50
        assert kg_item.relevance_score > 0.55

    def test_empty_kg_returns_trusted_only(self):
        trusted = [_make_item("finding", 0.87, f"f:{i}") for i in range(5)]
        source = HybridKGEvidenceSource(
            trusted_source=MockSource(trusted),
            kg_source=MockSource([]),
            min_trusted_quota=3,
            kg_diversification_quota=3,
        )
        items = source.gather("energy", limit=5)
        assert all(it.source_type == "finding" for it in items)


# ===========================================================================
# D. 3-Way Comparison Harness Tests
# ===========================================================================

class TestThreeWayComparison:
    def test_three_way_comparison(self):
        current = [_make_item("finding", 0.87, f"f:{i}") for i in range(5)]
        shadow = [_make_item("kg_segment", 0.55, f"kg:{i}") for i in range(5)]
        hybrid = [
            _make_item("finding", 0.87, "f:0"),
            _make_item("finding", 0.85, "f:1"),
            _make_item("kg_segment", 0.80, "kg:0"),
            _make_item("kg_segment", 0.78, "kg:1"),
            _make_item("kg_segment", 0.75, "kg:2"),
        ]

        harness = RetrievalComparisonHarness(
            current_source=MockSource(current),
            shadow_source=MockSource(shadow),
            hybrid_source=MockSource(hybrid),
        )
        result = harness.compare(domain="energy", limit=5)

        assert result.current_metrics is not None
        assert result.shadow_metrics is not None
        assert result.hybrid_metrics is not None
        assert result.hybrid_verdict != "not_tested"

        d = result.to_dict()
        assert "hybrid" in d
        assert "hybrid_verdict" in d

    def test_two_way_backward_compatible(self):
        current = [_make_item("finding", 0.87, "f:1")]
        shadow = [_make_item("kg_segment", 0.55, "kg:1")]
        harness = RetrievalComparisonHarness(
            current_source=MockSource(current),
            shadow_source=MockSource(shadow),
        )
        result = harness.compare(domain="energy", limit=5)
        assert result.hybrid_metrics is None
        assert result.hybrid_verdict == "not_tested"

    def test_comparison_result_to_dict_without_hybrid(self):
        result = ComparisonResult(
            domain="test",
            current_metrics=SourceMetrics(source_name="current", item_count=5),
            shadow_metrics=SourceMetrics(source_name="shadow", item_count=3),
        )
        d = result.to_dict()
        assert "hybrid" not in d
        assert d["hybrid_verdict"] == "not_tested"


# ===========================================================================
# E. Switch-Readiness Logic Tests
# ===========================================================================

class TestSwitchReadiness:
    """Test the switch_readiness function from the script logic."""

    def _make_comparison(
        self, current_rel: float, hybrid_rel: float,
        current_div: int, hybrid_div: int,
    ) -> dict:
        return {
            "current": {
                "mean_relevance": current_rel,
                "unique_source_ids": current_div,
                "source_type_counts": {"finding": 10},
            },
            "hybrid": {
                "mean_relevance": hybrid_rel,
                "unique_source_ids": hybrid_div,
                "source_type_counts": {"finding": 5, "kg_segment": 5},
            },
            "shadow": {
                "mean_relevance": 0.5,
                "unique_source_ids": 8,
                "source_type_counts": {"kg_segment": 10},
            },
        }

    def test_ready_when_all_pass(self):
        # Import the function from the script
        import importlib.util
        import os
        spec = importlib.util.spec_from_file_location(
            "phase10d", os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "phase10d_kg_hardening.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        comp = self._make_comparison(0.87, 0.87, 5, 8)
        decision = mod.switch_readiness(comp)
        assert decision["recommendation"] == "ready_for_limited_production_retrieval_ab"

    def test_keep_shadow_when_score_drops(self):
        import importlib.util
        import os
        spec = importlib.util.spec_from_file_location(
            "phase10d", os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "phase10d_kg_hardening.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        comp = self._make_comparison(0.87, 0.80, 5, 8)
        decision = mod.switch_readiness(comp)
        assert decision["recommendation"] == "keep_shadow_only"

    def test_keep_shadow_when_no_hybrid(self):
        import importlib.util
        import os
        spec = importlib.util.spec_from_file_location(
            "phase10d", os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "phase10d_kg_hardening.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        comp = {"current": {"mean_relevance": 0.87}, "shadow": {}}
        decision = mod.switch_readiness(comp)
        assert decision["recommendation"] == "keep_shadow_only"


# ===========================================================================
# F. Default Calibration Profiles
# ===========================================================================

class TestDefaultProfiles:
    def test_default_profiles_exist(self):
        assert "kg_segment" in DEFAULT_PROFILES
        assert "kg_graph" in DEFAULT_PROFILES
        assert "finding" in DEFAULT_PROFILES
        assert "paper" in DEFAULT_PROFILES

    def test_finding_is_near_identity(self):
        p = DEFAULT_PROFILES["finding"]
        # Findings should map ~identity
        assert abs(p.calibrate(0.87) - 0.87) < 0.02

    def test_kg_segment_calibrates_up(self):
        p = DEFAULT_PROFILES["kg_segment"]
        raw = 0.55
        calibrated = p.calibrate(raw)
        assert calibrated > raw
        assert calibrated >= 0.75
        assert calibrated <= 0.88
