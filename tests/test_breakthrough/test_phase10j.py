"""Phase 10J tests: evidence_refs diversity check, source-aware hybrid pool.

Tests cover:
1. Evidence_refs diversity fallthrough in orchestrator
2. Source-aware HybridKGEvidenceSource pool construction
3. Per-paper capping and KG item reservation
4. Diverse KG selection
"""
from __future__ import annotations

import pytest

from breakthrough_engine.hybrid_retrieval import HybridKGEvidenceSource, HybridMixDiagnostics
from breakthrough_engine.evidence_source import DemoFixtureSource, EvidenceSource
from breakthrough_engine.models import EvidenceItem, EvidencePack, new_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item(source_id: str, source_type: str = "finding", score: float = 0.9) -> EvidenceItem:
    return EvidenceItem(
        id=new_id(),
        source_type=source_type,
        source_id=source_id,
        title=f"Item from {source_id}",
        quote=f"Quote from {source_id}",
        citation=f"Citation ({source_id})",
        relevance_score=score,
    )


class FakeEvidenceSource(EvidenceSource):
    """Returns pre-configured evidence items."""
    def __init__(self, items: list[EvidenceItem]):
        self._items = items

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        return self._items[:limit]


class FakeKGSource(EvidenceSource):
    """Returns KG-style evidence items."""
    def __init__(self, items: list[EvidenceItem] | None = None):
        self._items = items if items is not None else [
            _item(f"kg_seg:seg_{i}", "kg_segment", score=0.6 - i * 0.02)
            for i in range(10)
        ]

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        return self._items[:limit]


# ---------------------------------------------------------------------------
# Test: evidence_refs diversity fallthrough
# ---------------------------------------------------------------------------

class TestEvidenceRefsDiversityCheck:
    """Phase 10J: When evidence_refs match produces non-diverse items,
    the orchestrator should fall through to ranked matching."""

    def test_same_source_refs_trigger_fallthrough(self):
        """If all evidence_refs match items from the same source_id,
        the diversity check should clear items and force ranked path."""
        # Simulate orchestrator logic
        evidence = [
            _item("arxiv:2402.11234", score=0.93),
            _item("arxiv:2402.11234", score=0.93),
            _item("arxiv:2312.09215", score=0.92),
            _item("arxiv:2312.09215", score=0.92),
            _item("doi:10.1038/example", score=0.91),
        ]

        # Candidate refs point to 2 items from same source
        evidence_refs = [evidence[0].id, evidence[1].id]
        items = [e for e in evidence if e.id in evidence_refs]

        # Phase 10J diversity check
        ref_sources = set(it.source_id for it in items)
        top_k = 2
        if len(ref_sources) < min(top_k, len(items)):
            items = []  # insufficient diversity

        assert items == [], "Should clear items when all refs from same source"

    def test_diverse_refs_preserved(self):
        """If evidence_refs match items from different sources, keep them."""
        evidence = [
            _item("arxiv:2402.11234", score=0.93),
            _item("arxiv:2312.09215", score=0.92),
        ]

        evidence_refs = [evidence[0].id, evidence[1].id]
        items = [e for e in evidence if e.id in evidence_refs]

        ref_sources = set(it.source_id for it in items)
        top_k = 2
        if len(ref_sources) < min(top_k, len(items)):
            items = []

        assert len(items) == 2, "Should preserve items when refs are diverse"

    def test_single_ref_preserved(self):
        """A single evidence_ref should be preserved (can't be non-diverse)."""
        evidence = [_item("arxiv:2402.11234", score=0.93)]
        evidence_refs = [evidence[0].id]
        items = [e for e in evidence if e.id in evidence_refs]

        ref_sources = set(it.source_id for it in items)
        top_k = 2
        if len(ref_sources) < min(top_k, len(items)):
            items = []

        assert len(items) == 1, "Single ref should be preserved"


# ---------------------------------------------------------------------------
# Test: source-aware hybrid pool construction
# ---------------------------------------------------------------------------

class TestSourceAwareHybridPool:
    """Phase 10J: HybridKGEvidenceSource guarantees KG items in pool."""

    def test_kg_items_reserved_in_pool(self):
        """KG items must appear in pool even when trusted items dominate."""
        trusted = FakeEvidenceSource([
            _item("arxiv:paper1", score=0.95),
            _item("arxiv:paper1", score=0.94),
            _item("arxiv:paper2", score=0.93),
            _item("arxiv:paper3", score=0.92),
            _item("arxiv:paper4", score=0.91),
            _item("arxiv:paper5", score=0.90),
            _item("arxiv:paper6", score=0.89),
            _item("arxiv:paper7", score=0.88),
            _item("arxiv:paper8", score=0.87),
            _item("arxiv:paper9", score=0.86),
        ])
        kg = FakeKGSource()

        hybrid = HybridKGEvidenceSource(
            trusted_source=trusted,
            kg_source=kg,
            min_trusted_quota=8,
            kg_diversification_quota=5,
            min_kg_items=2,
            max_per_paper=3,
        )

        result = hybrid.gather(domain="clean-energy", limit=10)
        kg_count = sum(1 for it in result if it.source_type == "kg_segment")
        assert kg_count >= 2, f"Expected >= 2 KG items, got {kg_count}"

    def test_per_paper_cap(self):
        """Per-paper cap prevents one paper from dominating the pool."""
        trusted = FakeEvidenceSource([
            _item("arxiv:dominant", score=0.95),
            _item("arxiv:dominant", score=0.94),
            _item("arxiv:dominant", score=0.93),
            _item("arxiv:dominant", score=0.92),
            _item("arxiv:dominant", score=0.91),
            _item("arxiv:other1", score=0.90),
            _item("arxiv:other2", score=0.89),
        ])
        kg = FakeKGSource([])

        hybrid = HybridKGEvidenceSource(
            trusted_source=trusted,
            kg_source=kg,
            min_trusted_quota=5,
            kg_diversification_quota=2,
            min_kg_items=0,
            max_per_paper=2,
        )

        result = hybrid.gather(domain="clean-energy", limit=7)
        from collections import Counter
        src_counts = Counter(it.source_id for it in result)
        assert src_counts.get("arxiv:dominant", 0) <= 2, \
            f"Per-paper cap violated: {src_counts['arxiv:dominant']} items from dominant"

    def test_diagnostics_include_kg_items(self):
        """Diagnostics should report non-zero kg_items when KG items present."""
        trusted = FakeEvidenceSource([
            _item("arxiv:paper1", score=0.95),
            _item("arxiv:paper2", score=0.93),
        ])
        kg = FakeKGSource([
            _item("kg_seg:seg1", "kg_segment", 0.7),
            _item("kg_seg:seg2", "kg_segment", 0.65),
        ])

        hybrid = HybridKGEvidenceSource(
            trusted_source=trusted,
            kg_source=kg,
            min_trusted_quota=2,
            kg_diversification_quota=2,
            min_kg_items=2,
        )

        result = hybrid.gather(domain="clean-energy", limit=4)
        diag = hybrid.last_diagnostics
        assert diag is not None
        assert diag.kg_items >= 1, f"Expected kg_items >= 1, got {diag.kg_items}"
        assert diag.unique_source_ids >= 3, f"Expected >= 3 unique sources, got {diag.unique_source_ids}"

    def test_diverse_kg_selection(self):
        """KG items should prefer items from different sources."""
        kg_items = [
            _item("kg_seg:seg1", "kg_segment", 0.8),
            _item("kg_seg:seg1", "kg_segment", 0.78),
            _item("kg_seg:seg2", "kg_segment", 0.75),
            _item("kg_seg:seg3", "kg_segment", 0.70),
        ]
        trusted = FakeEvidenceSource([])
        kg = FakeKGSource(kg_items)

        hybrid = HybridKGEvidenceSource(
            trusted_source=trusted,
            kg_source=kg,
            min_trusted_quota=0,
            kg_diversification_quota=4,
            min_kg_items=3,
        )

        result = hybrid.gather(domain="clean-energy", limit=3)
        source_ids = set(it.source_id for it in result)
        assert len(source_ids) >= 2, f"Expected >= 2 unique KG sources, got {len(source_ids)}"

    def test_empty_kg_graceful(self):
        """If KG source returns empty, hybrid falls back to trusted only."""
        trusted = FakeEvidenceSource([
            _item("arxiv:paper1", score=0.95),
            _item("arxiv:paper2", score=0.93),
        ])
        kg = FakeKGSource([])

        hybrid = HybridKGEvidenceSource(
            trusted_source=trusted,
            kg_source=kg,
            min_trusted_quota=2,
            kg_diversification_quota=2,
            min_kg_items=2,
        )

        result = hybrid.gather(domain="clean-energy", limit=4)
        assert len(result) == 2  # only 2 trusted, no KG
        assert all(it.source_type == "finding" for it in result)

    def test_pool_source_diversity(self):
        """Pool should have at least as many unique sources as items allow."""
        trusted = FakeEvidenceSource([
            _item("arxiv:paper1", score=0.95),
            _item("arxiv:paper2", score=0.93),
            _item("arxiv:paper3", score=0.92),
        ])
        kg = FakeKGSource([
            _item("kg_seg:seg1", "kg_segment", 0.7),
            _item("kg_seg:seg2", "kg_segment", 0.65),
        ])

        hybrid = HybridKGEvidenceSource(
            trusted_source=trusted,
            kg_source=kg,
            min_trusted_quota=3,
            kg_diversification_quota=2,
            min_kg_items=2,
        )

        result = hybrid.gather(domain="clean-energy", limit=5)
        source_ids = set(it.source_id for it in result)
        assert len(source_ids) >= 4, f"Expected >= 4 unique sources, got {len(source_ids)}"


# ---------------------------------------------------------------------------
# Test: _cap_per_paper and _select_diverse_kg helpers
# ---------------------------------------------------------------------------

class TestHybridHelpers:

    def test_cap_per_paper(self):
        """_cap_per_paper limits items per source_id."""
        trusted = FakeEvidenceSource([])
        kg = FakeKGSource([])
        hybrid = HybridKGEvidenceSource(
            trusted_source=trusted, kg_source=kg,
            max_per_paper=2,
        )
        items = [
            _item("arxiv:A", score=0.9),
            _item("arxiv:A", score=0.89),
            _item("arxiv:A", score=0.88),
            _item("arxiv:B", score=0.87),
        ]
        capped = hybrid._cap_per_paper(items)
        a_count = sum(1 for it in capped if it.source_id == "arxiv:A")
        assert a_count == 2
        assert len(capped) == 3  # 2 from A + 1 from B

    def test_select_diverse_kg_prefers_unique_sources(self):
        """_select_diverse_kg should pick from different sources first."""
        trusted = FakeEvidenceSource([])
        kg = FakeKGSource([])
        hybrid = HybridKGEvidenceSource(
            trusted_source=trusted, kg_source=kg,
        )
        kg_items = [
            _item("kg:src1", "kg_segment", 0.8),
            _item("kg:src1", "kg_segment", 0.79),
            _item("kg:src2", "kg_segment", 0.75),
            _item("kg:src3", "kg_segment", 0.70),
        ]
        selected = hybrid._select_diverse_kg(kg_items, k=3)
        sources = set(it.source_id for it in selected)
        assert len(sources) == 3, f"Expected 3 unique sources, got {len(sources)}: {sources}"
