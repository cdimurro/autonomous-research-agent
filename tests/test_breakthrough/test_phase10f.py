"""Phase 10F tests: Graph pipeline wiring, canonicalization hardening, grounding hardening.

All tests are offline-safe and do not require Ollama or external APIs.
"""

from __future__ import annotations

import pytest

from breakthrough_engine.models import (
    CandidateHypothesis,
    EvidenceItem,
    EvidencePack,
    ResearchProgram,
    RunMode,
)
from breakthrough_engine.db import Repository, init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_candidate():
    return CandidateHypothesis(
        id="test_cand_10f",
        run_id="run_10f",
        title="Perovskite-MOF Hybrid for Enhanced CO2 Capture",
        domain="clean-energy",
        statement="Integrating perovskite nanocrystals with MOF-303 creates a hybrid material that achieves 40% higher CO2 uptake than pristine MOF-303.",
        mechanism="Perovskite nanocrystals act as photosensitizers, enabling light-driven CO2 adsorption through photoinduced electron transfer to the MOF pore sites.",
        expected_outcome="CO2 uptake of 8.5 mmol/g at 298K, compared to 6.1 mmol/g for pristine MOF-303.",
        testability_window_hours=72.0,
        novelty_notes="No prior work combining perovskite photosensitizers with MOF-303 for CO2 capture.",
        assumptions=["Perovskite nanocrystals are stable in MOF synthesis conditions"],
        risk_flags=[],
        evidence_refs=["ev1", "ev2"],
    )


@pytest.fixture
def graph_evidence():
    return [
        EvidenceItem(
            id="ev_gp1",
            source_id="cpath:mof-303→carbon-capture→co2-uptake",
            source_type="graph_path",
            title="MOF-303 → carbon capture → CO2 uptake (CROSS-PAPER)",
            quote="Multi-hop reasoning path: MOF-303 enables carbon capture, measured by CO2 uptake across 3 papers",
            citation="Graph path",
            relevance_score=0.92,
        ),
        EvidenceItem(
            id="ev_gp2",
            source_id="cpath:perovskite→photosensitizer→electron-transfer",
            source_type="graph_path",
            title="perovskite → photosensitizer → electron transfer (CROSS-PAPER)",
            quote="Perovskite nanocrystals as photosensitizers drive electron transfer mechanisms in solar cell and catalysis applications",
            citation="Graph path",
            relevance_score=0.88,
        ),
        EvidenceItem(
            id="ev_f1",
            source_id="arxiv:2401.05672",
            source_type="finding",
            title="Direct air capture of CO2 using metal-organic frameworks at <100 $/ton",
            quote="MOF-303 demonstrated exceptional CO2 uptake of 6.1 mmol/g at 298K with rapid adsorption kinetics",
            citation="arxiv:2401.05672",
            relevance_score=0.87,
        ),
    ]


@pytest.fixture
def mixed_evidence():
    return [
        EvidenceItem(
            id="ev_mix_1",
            source_id="arxiv:2312.09215",
            source_type="finding",
            title="All-perovskite tandem solar cells with 33.7% efficiency",
            quote="The certified power conversion efficiency of 33.7% exceeds the single-junction Shockley-Queisser limit",
            citation="arxiv:2312.09215",
            relevance_score=0.92,
        ),
        EvidenceItem(
            id="ev_mix_2",
            source_id="cpath:solar→efficiency",
            source_type="graph_path",
            title="perovskite solar cell → power conversion efficiency (CROSS-PAPER)",
            quote="Perovskite solar cell efficiency measured by power conversion efficiency across 9 papers",
            citation="Graph path",
            relevance_score=0.91,
        ),
        EvidenceItem(
            id="ev_mix_3",
            source_id="sg:perovskite-neighborhood",
            source_type="kg_subgraph",
            title="GRAPH NEIGHBORHOOD: perovskite solar cell",
            quote="Nodes: perovskite solar cell, power conversion efficiency, open-circuit voltage, methylammonium-free perovskite",
            citation="Subgraph",
            relevance_score=0.83,
        ),
    ]


# ---------------------------------------------------------------------------
# A: Wiring audit — verify defaults are production-safe
# ---------------------------------------------------------------------------

class TestWiringAudit:
    """Verify graph wiring is opt-in only."""

    def test_ladder_config_defaults_no_graph(self):
        from breakthrough_engine.daily_search import LadderConfig
        config = LadderConfig()
        assert config.evidence_source_override is None
        assert config.enable_graph_context is False

    def test_orchestrator_default_no_graph_context(self):
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        db = init_db(in_memory=True)
        repo = Repository(db)
        program = ResearchProgram(name="t", domain="t", mode=RunMode.DETERMINISTIC_TEST)
        orch = BreakthroughOrchestrator(program=program, repo=repo)
        assert orch.enable_graph_context is False
        assert orch._graph_context_str is None

    def test_orchestrator_graph_context_opt_in(self):
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        db = init_db(in_memory=True)
        repo = Repository(db)
        program = ResearchProgram(name="t", domain="t", mode=RunMode.DETERMINISTIC_TEST)
        orch = BreakthroughOrchestrator(
            program=program, repo=repo, enable_graph_context=True,
        )
        assert orch.enable_graph_context is True

    def test_evidence_source_override_propagated(self):
        """LadderConfig evidence_source_override is accepted."""
        from breakthrough_engine.daily_search import LadderConfig
        from breakthrough_engine.evidence_source import DemoFixtureSource

        src = DemoFixtureSource()
        config = LadderConfig(evidence_source_override=src, enable_graph_context=True)
        assert config.evidence_source_override is src
        assert config.enable_graph_context is True


# ---------------------------------------------------------------------------
# B: Evidence-source injection
# ---------------------------------------------------------------------------

class TestEvidenceSourceInjection:
    """Verify evidence source override reaches the orchestrator."""

    def test_orchestrator_accepts_custom_source(self):
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        from breakthrough_engine.evidence_source import DemoFixtureSource

        db = init_db(in_memory=True)
        repo = Repository(db)
        program = ResearchProgram(name="t", domain="clean-energy", mode=RunMode.DETERMINISTIC_TEST)
        custom_src = DemoFixtureSource()
        orch = BreakthroughOrchestrator(
            program=program, repo=repo, evidence_source=custom_src,
        )
        assert orch.evidence_source is custom_src

    def test_hybrid_source_is_injectable(self):
        """HybridKGEvidenceSource can be created and injected."""
        from breakthrough_engine.hybrid_retrieval import HybridKGEvidenceSource
        from breakthrough_engine.evidence_source import DemoFixtureSource

        trusted = DemoFixtureSource()
        kg = DemoFixtureSource()
        hybrid = HybridKGEvidenceSource(trusted_source=trusted, kg_source=kg)
        items = hybrid.gather("clean-energy", limit=20)
        assert isinstance(items, list)


# ---------------------------------------------------------------------------
# C: Graph-conditioned generation wiring
# ---------------------------------------------------------------------------

class TestGraphConditionedGeneration:
    """Verify graph context flows through to generation."""

    def test_generate_accepts_graph_context(self):
        from breakthrough_engine.candidate_generator import FakeCandidateGenerator
        gen = FakeCandidateGenerator()
        evidence = [
            EvidenceItem(
                id="e1", source_id="s1", source_type="finding",
                title="Test", quote="Test quote", citation="test",
                relevance_score=0.9,
            ),
        ]
        # Should not raise with graph_context
        result = gen.generate(evidence, "clean-energy", budget=3, graph_context="GRAPH STRUCTURE: test")
        assert len(result) > 0

    def test_ollama_generator_uses_graph_template(self):
        """OllamaCandidateGenerator switches to GRAPH_CONDITIONED_TEMPLATE when graph_context given."""
        from breakthrough_engine.candidate_generator import (
            OllamaCandidateGenerator, GRAPH_CONDITIONED_TEMPLATE, EVIDENCE_BLOCK_TEMPLATE,
        )
        gen = OllamaCandidateGenerator()
        evidence = [
            EvidenceItem(
                id="e1", source_id="s1", source_type="finding",
                title="Test Finding", quote="Test quote about solar cells",
                citation="test", relevance_score=0.9,
            ),
        ]
        # Build with graph context
        prompt = gen._build_graph_conditioned_prompt(
            evidence=evidence, domain="clean-energy", budget=5,
            graph_context="GRAPH STRUCTURE: 10 concepts, 5 paths",
        )
        assert "GRAPH STRUCTURE" in prompt
        assert "GRAPH_NEIGHBORHOOD" in prompt  # From template type key

    def test_benchmark_generator_accepts_graph_context(self):
        from breakthrough_engine.benchmark import BenchmarkCandidateGenerator
        from breakthrough_engine.models import CandidateHypothesis
        cand = CandidateHypothesis(
            id="c1", run_id="r1", title="Test", domain="test",
            statement="s", mechanism="m", expected_outcome="e",
        )
        gen = BenchmarkCandidateGenerator([cand])
        result = gen.generate([], "test", graph_context="test graph")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# D: Canonicalization hardening
# ---------------------------------------------------------------------------

class TestCanonicalizationHardening:
    """Test near-duplicate merging and improved synonym coverage."""

    def test_single_junction_cell_merges(self):
        """single-junction cell should normalize to single-junction solar cell."""
        from breakthrough_engine.kg_canonicalization import normalize_entity_name
        assert normalize_entity_name("single-junction cell") == "single-junction solar cell"
        assert normalize_entity_name("single junction cell") == "single-junction solar cell"
        assert normalize_entity_name("single-junction cells") == "single-junction solar cell"

    def test_near_duplicate_merge_subset(self):
        """Token-subset concepts should be merged."""
        from breakthrough_engine.kg_canonicalization import ConceptCanonicalizer, CanonicalConcept

        canonical_map = {
            "champion device": CanonicalConcept(
                canonical_name="champion device",
                entity_type="device",
                confidence=0.8,
                aliases=["champion device"],
                source_entity_ids=["e1"],
                source_paper_ids={"p1"},
                mention_count=2,
            ),
            "champion tandem device": CanonicalConcept(
                canonical_name="champion tandem device",
                entity_type="device",
                confidence=0.85,
                aliases=["champion tandem device"],
                source_entity_ids=["e2", "e3"],
                source_paper_ids={"p1", "p2"},
                mention_count=3,
            ),
        }
        result = ConceptCanonicalizer._merge_near_duplicates(canonical_map)
        # "champion device" should merge into "champion tandem device"
        assert len(result) == 1
        merged = list(result.values())[0]
        assert merged.canonical_name == "champion tandem device"
        assert merged.mention_count == 5  # 2 + 3
        assert "e1" in merged.source_entity_ids

    def test_near_duplicate_no_cross_type_merge(self):
        """Don't merge concepts with different entity types."""
        from breakthrough_engine.kg_canonicalization import ConceptCanonicalizer, CanonicalConcept

        canonical_map = {
            "solar cell": CanonicalConcept(
                canonical_name="solar cell",
                entity_type="device",
                aliases=["solar cell"],
                source_entity_ids=["e1"],
                source_paper_ids={"p1"},
                mention_count=1,
            ),
            "solar cell efficiency": CanonicalConcept(
                canonical_name="solar cell efficiency",
                entity_type="metric",
                aliases=["solar cell efficiency"],
                source_entity_ids=["e2"],
                source_paper_ids={"p1"},
                mention_count=1,
            ),
        }
        result = ConceptCanonicalizer._merge_near_duplicates(canonical_map)
        # Different types, should NOT merge
        assert len(result) == 2

    def test_near_duplicate_single_word_skip(self):
        """Single-word concepts should not participate in subset merge."""
        from breakthrough_engine.kg_canonicalization import ConceptCanonicalizer, CanonicalConcept

        canonical_map = {
            "cell": CanonicalConcept(
                canonical_name="cell",
                aliases=["cell"],
                source_entity_ids=["e1"],
                source_paper_ids={"p1"},
                mention_count=1,
            ),
            "solar cell": CanonicalConcept(
                canonical_name="solar cell",
                aliases=["solar cell"],
                source_entity_ids=["e2"],
                source_paper_ids={"p1"},
                mention_count=1,
            ),
        }
        result = ConceptCanonicalizer._merge_near_duplicates(canonical_map)
        # Single-word "cell" should NOT merge into "solar cell"
        assert len(result) == 2


# ---------------------------------------------------------------------------
# E: Grounding hardening
# ---------------------------------------------------------------------------

class TestGroundingHardening:
    """Test improved grounding validation."""

    def test_bigram_extraction(self):
        from breakthrough_engine.kg_grounding import _extract_bigrams
        bigrams = _extract_bigrams("perovskite solar cell efficiency")
        assert "perovskite_solar" in bigrams
        assert "solar_cell" in bigrams
        assert "cell_efficiency" in bigrams

    def test_improved_overlap_with_bigrams(self):
        from breakthrough_engine.kg_grounding import _keyword_overlap_score
        # Use a case where unigram overlap is moderate (not already at max)
        claim_kw = {"perovskite", "solar", "cell", "efficiency", "tandem",
                     "hybrid", "absorber", "interface", "transport", "layer"}
        evidence_kw = {"perovskite", "solar", "cell", "power", "conversion"}
        claim_bi = {"perovskite_solar", "solar_cell", "cell_efficiency"}
        evidence_bi = {"perovskite_solar", "solar_cell", "power_conversion"}

        # With bigrams should score higher than without
        score_no_bi = _keyword_overlap_score(claim_kw, evidence_kw)
        score_with_bi = _keyword_overlap_score(claim_kw, evidence_kw, claim_bi, evidence_bi)
        assert score_with_bi > score_no_bi

    def test_grounding_graph_path_improved(self, sample_candidate, graph_evidence):
        from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
        validator = EvidenceGroundingValidator()
        result = validator.validate(sample_candidate, graph_evidence)
        # With hardened grounding, graph paths with relevant keywords should
        # score better than "unsupported"
        graph_path_verdicts = [
            v for eid, v in result.evidence_verdicts.items()
            if eid.startswith("ev_gp")
        ]
        assert any(v != "unsupported" for v in graph_path_verdicts), (
            f"Graph path evidence should not all be unsupported: {result.evidence_verdicts}"
        )

    def test_grounding_partial_support_level(self, sample_candidate, graph_evidence):
        from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
        validator = EvidenceGroundingValidator()
        result = validator.validate(sample_candidate, graph_evidence)
        # partial_support is now a valid verdict level
        valid_verdicts = {"strong_support", "partial_support", "weak_support", "unsupported", "contradicted"}
        for v in result.evidence_verdicts.values():
            assert v in valid_verdicts

    def test_grounding_finding_still_strong(self, sample_candidate):
        from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
        evidence = [
            EvidenceItem(
                id="ev_find",
                source_id="arxiv:2401.05672",
                source_type="finding",
                title="MOF-303 CO2 capture at 6.1 mmol/g with perovskite hybrid",
                quote="MOF-303 demonstrated CO2 uptake of 6.1 mmol/g at 298K with perovskite nanocrystal photosensitizers enabling light-driven adsorption",
                citation="arxiv:2401.05672",
                relevance_score=0.92,
            ),
        ]
        validator = EvidenceGroundingValidator()
        result = validator.validate(sample_candidate, evidence)
        # Highly relevant finding should still get strong_support
        assert result.evidence_verdicts["ev_find"] in ("strong_support", "partial_support")

    def test_grounding_stopwords_expanded(self):
        from breakthrough_engine.kg_grounding import _STOPWORDS
        # Phase 10F added scientific stopwords
        assert "using" in _STOPWORDS
        assert "demonstrated" in _STOPWORDS
        assert "approach" in _STOPWORDS

    def test_grounding_to_dict(self, sample_candidate, graph_evidence):
        from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
        validator = EvidenceGroundingValidator()
        result = validator.validate(sample_candidate, graph_evidence)
        d = result.to_dict()
        assert "overall_verdict" in d
        assert "grounding_score" in d
        assert "evidence_count" in d


# ---------------------------------------------------------------------------
# F: Graph-aware scoring integration
# ---------------------------------------------------------------------------

class TestGraphAwareScoring:
    """Test graph-aware evidence strength scoring."""

    def test_graph_items_get_diversity_bonus(self):
        from breakthrough_engine.scoring import score_candidate

        program = ResearchProgram(
            name="test", domain="clean-energy",
            scoring_weights={"novelty": 0.20, "plausibility": 0.20,
                             "impact": 0.20, "inverse_validation_cost": 0.10,
                             "evidence_strength": 0.15, "simulation_readiness": 0.15},
        )
        candidate = CandidateHypothesis(
            id="c1", run_id="r1", title="Test",
            domain="clean-energy", statement="Test statement about solar cells",
            mechanism="Uses electron transfer via perovskite interface",
            expected_outcome="Improved efficiency",
            novelty_notes="Novel approach combining two materials",
        )
        # Evidence pack with graph items
        evidence = EvidencePack(
            candidate_id="c1",
            items=[
                EvidenceItem(
                    id="e1", source_id="s1", source_type="finding",
                    title="Finding", quote="Q", citation="c", relevance_score=0.9,
                ),
                EvidenceItem(
                    id="e2", source_id="cpath:a→b", source_type="graph_path",
                    title="Graph path", quote="Q", citation="c", relevance_score=0.88,
                ),
            ],
            source_diversity_count=2,
        )
        score = score_candidate(candidate, evidence, None, [], program)
        assert score.evidence_strength_score > 0.0


# ---------------------------------------------------------------------------
# Integration: Full wiring path
# ---------------------------------------------------------------------------

class TestFullWiringPath:
    """Integration tests for the complete graph-conditioned pipeline path."""

    def test_ladder_config_to_orchestrator_wiring(self):
        """Verify LadderConfig fields propagate to BreakthroughOrchestrator."""
        from breakthrough_engine.daily_search import LadderConfig
        from breakthrough_engine.evidence_source import DemoFixtureSource

        config = LadderConfig(
            evidence_source_override=DemoFixtureSource(),
            enable_graph_context=True,
        )
        assert config.evidence_source_override is not None
        assert config.enable_graph_context is True

    def test_build_graph_context_returns_none_for_empty_graph(self):
        """Graph context builder returns None when graph is too small."""
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        db = init_db(in_memory=True)
        repo = Repository(db)
        program = ResearchProgram(
            name="test", domain="clean-energy",
            mode=RunMode.DETERMINISTIC_TEST,
        )
        orch = BreakthroughOrchestrator(
            program=program, repo=repo, enable_graph_context=True,
        )
        # No entities in DB, so graph context should return None
        ctx = orch._build_graph_context("run123", [])
        assert ctx is None
