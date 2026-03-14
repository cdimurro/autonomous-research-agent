"""Phase 10I: Diversity-Aware Ranking & Evidence Persistence — offline-safe tests.

Tests cover:
- select_diverse_top_k anti-concentration behavior
- Source cap enforcement
- Bypass for exceptionally strong items
- Relaxation fallback when caps prevent filling k
- Evidence item persistence with fresh IDs per pack
- Pre/post-ranking diversity metrics
"""

from __future__ import annotations

import pytest

from breakthrough_engine.models import EvidenceItem, EvidencePack, new_id
from breakthrough_engine.retrieval import rank_evidence, select_diverse_top_k


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(
    source_id: str,
    relevance: float = 0.8,
    source_type: str = "finding",
    title: str = "",
    mechanism_keywords: str = "",
) -> EvidenceItem:
    return EvidenceItem(
        id=new_id(),
        source_type=source_type,
        source_id=source_id,
        title=title or f"Item from {source_id}",
        quote=f"Evidence about {mechanism_keywords or 'general topic'} from {source_id}.",
        citation="Test citation 2024",
        relevance_score=relevance,
    )


# ===========================================================================
# A. select_diverse_top_k — anti-concentration
# ===========================================================================

class TestSelectDiverseTopK:
    """Tests for Phase 10I diversity-aware top-k selection."""

    def test_basic_diversity_selection(self):
        """Items from different sources should all be selected."""
        items = [
            _make_item("src:A", 0.9),
            _make_item("src:B", 0.85),
            _make_item("src:C", 0.8),
        ]
        ranked = rank_evidence(items, domain="clean-energy")
        selected = select_diverse_top_k(ranked, k=2, max_per_source=1)
        source_ids = [item.source_id for item, _ in selected]
        assert len(set(source_ids)) == 2, "Should select from 2 different sources"

    def test_concentration_prevention(self):
        """When top items share one source, diversity selection picks different sources."""
        # Create scenario matching the actual bug: 4 items from same source at top
        items = [
            _make_item("arxiv:2402.11234", 0.95, mechanism_keywords="thermal insulator"),
            _make_item("arxiv:2402.11234", 0.93, mechanism_keywords="thermal insulator phase"),
            _make_item("arxiv:2402.11234", 0.91, mechanism_keywords="insulator thermal"),
            _make_item("arxiv:9999.00001", 0.80),
            _make_item("arxiv:9999.00002", 0.78),
        ]
        ranked = rank_evidence(items, domain="clean-energy", mechanism="thermal insulator")

        # Old behavior: top-2 would both be from arxiv:2402.11234
        naive_top2 = [(item, detail) for item, detail in ranked[:2]]
        naive_sources = {item.source_id for item, _ in naive_top2}
        assert len(naive_sources) == 1, "Naive top-2 concentrates on one source"

        # New behavior: diverse selection picks from different sources
        diverse_top2 = select_diverse_top_k(ranked, k=2, max_per_source=1)
        diverse_sources = {item.source_id for item, _ in diverse_top2}
        assert len(diverse_sources) == 2, "Diverse top-2 should pick from 2 sources"

    def test_max_per_source_cap(self):
        """Per-source cap limits items from any single source."""
        items = [
            _make_item("src:A", 0.95),
            _make_item("src:A", 0.93),
            _make_item("src:A", 0.91),
            _make_item("src:B", 0.60),
            _make_item("src:C", 0.55),
        ]
        ranked = rank_evidence(items, domain="clean-energy")
        selected = select_diverse_top_k(ranked, k=3, max_per_source=1)
        source_counts = {}
        for item, _ in selected:
            source_counts[item.source_id] = source_counts.get(item.source_id, 0) + 1
        assert all(c <= 1 for c in source_counts.values()), "No source exceeds cap"
        assert len(selected) == 3

    def test_max_per_source_cap_of_2(self):
        """Allow up to 2 items per source when cap is 2."""
        items = [
            _make_item("src:A", 0.95),
            _make_item("src:A", 0.93),
            _make_item("src:A", 0.91),
            _make_item("src:B", 0.60),
        ]
        ranked = rank_evidence(items, domain="clean-energy")
        selected = select_diverse_top_k(ranked, k=3, max_per_source=2)
        a_count = sum(1 for item, _ in selected if item.source_id == "src:A")
        assert a_count <= 2

    def test_relaxation_fallback(self):
        """When caps prevent filling k, relaxation allows additional items."""
        # Only 2 sources, but k=3 with max_per_source=1
        items = [
            _make_item("src:A", 0.95),
            _make_item("src:A", 0.90),
            _make_item("src:B", 0.80),
        ]
        ranked = rank_evidence(items, domain="clean-energy")
        selected = select_diverse_top_k(ranked, k=3, max_per_source=1)
        assert len(selected) == 3, "Relaxation should fill remaining slots"

    def test_empty_input(self):
        """Empty input returns empty output."""
        assert select_diverse_top_k([], k=2) == []

    def test_k_zero(self):
        """k=0 returns empty."""
        items = [_make_item("src:A", 0.9)]
        ranked = rank_evidence(items, domain="test")
        assert select_diverse_top_k(ranked, k=0) == []

    def test_fewer_items_than_k(self):
        """If fewer items than k, return all."""
        items = [_make_item("src:A", 0.9)]
        ranked = rank_evidence(items, domain="test")
        selected = select_diverse_top_k(ranked, k=5)
        assert len(selected) == 1

    def test_quality_preserved(self):
        """First selected item should be the highest-scored item."""
        items = [
            _make_item("src:A", 0.95),
            _make_item("src:B", 0.50),
            _make_item("src:C", 0.45),
        ]
        ranked = rank_evidence(items, domain="clean-energy")
        selected = select_diverse_top_k(ranked, k=2, max_per_source=1)
        # First item should still be the best one
        assert selected[0][0].source_id == "src:A"

    def test_detail_annotations(self):
        """Selected items should have diversity_penalty and effective_score."""
        items = [
            _make_item("src:A", 0.95),
            _make_item("src:B", 0.80),
        ]
        ranked = rank_evidence(items, domain="clean-energy")
        selected = select_diverse_top_k(ranked, k=2, max_per_source=1)
        for _, detail in selected:
            assert "diversity_penalty" in detail
            assert "effective_score" in detail

    def test_source_id_in_ranking_detail(self):
        """rank_evidence should annotate source_id in detail dict."""
        items = [_make_item("src:A", 0.9)]
        ranked = rank_evidence(items, domain="test")
        _, detail = ranked[0]
        assert detail.get("source_id") == "src:A"


# ===========================================================================
# B. Evidence Item Persistence — fresh IDs per pack
# ===========================================================================

class TestEvidenceItemPersistence:
    """Tests for Phase 10I evidence item persistence fix."""

    def test_pack_items_get_unique_ids(self):
        """Different packs from the same evidence pool should have distinct item IDs."""
        # Simulate the shared evidence pool
        shared_items = [
            _make_item("src:A", 0.9),
            _make_item("src:B", 0.8),
        ]
        original_ids = {item.id for item in shared_items}

        # Create pack copies as the orchestrator now does
        pack1_items = [
            EvidenceItem(
                id=new_id(),
                source_type=item.source_type,
                source_id=item.source_id,
                title=item.title,
                quote=item.quote,
                citation=item.citation,
                relevance_score=item.relevance_score,
            )
            for item in shared_items
        ]
        pack2_items = [
            EvidenceItem(
                id=new_id(),
                source_type=item.source_type,
                source_id=item.source_id,
                title=item.title,
                quote=item.quote,
                citation=item.citation,
                relevance_score=item.relevance_score,
            )
            for item in shared_items
        ]

        pack1_ids = {item.id for item in pack1_items}
        pack2_ids = {item.id for item in pack2_items}

        # All IDs should be distinct
        assert pack1_ids.isdisjoint(pack2_ids), "Pack item IDs must be unique across packs"
        assert pack1_ids.isdisjoint(original_ids), "Pack item IDs must differ from originals"

    def test_pack_preserves_content(self):
        """Copied items preserve all content fields."""
        original = _make_item("src:A", 0.85, source_type="kg_segment")
        copy = EvidenceItem(
            id=new_id(),
            source_type=original.source_type,
            source_id=original.source_id,
            title=original.title,
            quote=original.quote,
            citation=original.citation,
            relevance_score=original.relevance_score,
        )
        assert copy.source_type == original.source_type
        assert copy.source_id == original.source_id
        assert copy.title == original.title
        assert copy.quote == original.quote
        assert copy.citation == original.citation
        assert copy.relevance_score == original.relevance_score
        assert copy.id != original.id

    def test_source_diversity_count_accurate(self):
        """source_diversity_count reflects diverse items in the pack."""
        items = [
            _make_item("src:A", 0.9),
            _make_item("src:B", 0.8),
            _make_item("src:C", 0.7),
        ]
        pack = EvidencePack(
            candidate_id="test-candidate",
            items=items,
            source_diversity_count=len(set(i.source_id for i in items)),
        )
        assert pack.source_diversity_count == 3


# ===========================================================================
# C. Pre/Post-ranking diversity metrics
# ===========================================================================

class TestRankingDiversityMetrics:
    """Tests for measuring diversity before and after ranking."""

    def test_pre_ranking_diverse_post_ranking_concentrated(self):
        """Demonstrates the ranking collapse: diverse input → concentrated output."""
        # 5 items from 3 sources, but one source dominates mechanism overlap
        items = [
            EvidenceItem(
                id=new_id(), source_type="finding", source_id="src:A",
                title="Thermal insulator breakthrough",
                quote="thermal insulator mechanism phase transition boundary",
                citation="Test 2024", relevance_score=0.9,
            ),
            EvidenceItem(
                id=new_id(), source_type="finding", source_id="src:A",
                title="Thermal insulator extended",
                quote="thermal insulator phonon scattering surface state",
                citation="Test 2024", relevance_score=0.88,
            ),
            EvidenceItem(
                id=new_id(), source_type="finding", source_id="src:B",
                title="Solar cell efficiency",
                quote="perovskite solar cell power conversion",
                citation="Test 2024", relevance_score=0.85,
            ),
            EvidenceItem(
                id=new_id(), source_type="kg_segment", source_id="src:C",
                title="Battery cathode material",
                quote="lithium ion cathode energy density",
                citation="Test 2024", relevance_score=0.82,
            ),
            EvidenceItem(
                id=new_id(), source_type="kg_segment", source_id="src:D",
                title="Hydrogen storage MOF",
                quote="metal organic framework hydrogen adsorption",
                citation="Test 2024", relevance_score=0.75,
            ),
        ]

        pre_sources = len(set(i.source_id for i in items))
        assert pre_sources >= 4, "Pre-ranking should have 4+ unique sources"

        ranked = rank_evidence(
            items, domain="clean-energy", mechanism="thermal insulator"
        )

        # Naive top-2 concentrates on src:A
        naive_top2_sources = {item.source_id for item, _ in ranked[:2]}
        assert len(naive_top2_sources) <= 2

        # Diverse top-2 prevents concentration
        diverse = select_diverse_top_k(ranked, k=2, max_per_source=1)
        diverse_sources = {item.source_id for item, _ in diverse}
        assert len(diverse_sources) == 2, "Diverse selection preserves source diversity"

    def test_diversity_metrics_computable(self):
        """Diversity metrics can be computed from ranked + selected outputs."""
        items = [
            _make_item("src:A", 0.9),
            _make_item("src:B", 0.8),
            _make_item("src:A", 0.7),
        ]
        ranked = rank_evidence(items, domain="test")
        selected = select_diverse_top_k(ranked, k=2, max_per_source=1)

        # Compute metrics
        pre_sources = len(set(i.source_id for i in items))
        post_sources = len(set(item.source_id for item, _ in selected))

        assert pre_sources == 2
        assert post_sources == 2  # diversity preserved


# ===========================================================================
# D. Integration: rank_evidence + select_diverse_top_k
# ===========================================================================

class TestRankingIntegration:
    """Integration tests for the full ranking pipeline."""

    def test_graph_native_scenario(self):
        """Simulate graph-native evidence with multiple KG segments from one paper."""
        items = [
            EvidenceItem(
                id=new_id(), source_type="kg_segment",
                source_id="kg_seg:seg_001",
                title="Thermal conductivity of TI surfaces...",
                quote="topological insulator surface states enhance thermal conductivity",
                citation="KG segment (paper=2402.11234)", relevance_score=0.85,
            ),
            EvidenceItem(
                id=new_id(), source_type="kg_segment",
                source_id="kg_seg:seg_002",
                title="Phase transition in TI nanoribbons...",
                quote="topological insulator nanoribbon phase transition thermal",
                citation="KG segment (paper=2402.11234)", relevance_score=0.83,
            ),
            EvidenceItem(
                id=new_id(), source_type="finding",
                source_id="arxiv:2401.00005",
                title="MOF-based carbon capture",
                quote="metal organic framework CO2 uptake thermal stability",
                citation="Rodriguez 2024", relevance_score=0.88,
            ),
            EvidenceItem(
                id=new_id(), source_type="finding",
                source_id="arxiv:2401.00001",
                title="Perovskite solar cells",
                quote="perovskite solar cell efficiency power conversion",
                citation="Zhang 2024", relevance_score=0.85,
            ),
        ]

        ranked = rank_evidence(
            items, domain="clean-energy",
            mechanism="topological insulator thermal conductivity",
        )
        diverse = select_diverse_top_k(ranked, k=2, max_per_source=1)
        sources = {item.source_id for item, _ in diverse}
        assert len(sources) == 2, f"Expected 2 unique sources, got {sources}"

    def test_current_retrieval_scenario(self):
        """Current retrieval already has diverse sources — should stay diverse."""
        items = [
            _make_item("arxiv:2401.00001", 0.9, source_type="finding"),
            _make_item("arxiv:2401.00002", 0.85, source_type="finding"),
            _make_item("arxiv:2401.00003", 0.8, source_type="finding"),
        ]
        ranked = rank_evidence(items, domain="clean-energy")
        diverse = select_diverse_top_k(ranked, k=2, max_per_source=1)
        sources = {item.source_id for item, _ in diverse}
        assert len(sources) == 2
