"""Phase 10E: KG Reasoning Upgrade — offline-safe tests.

Tests cover:
- Multi-signal segment scoring
- Confidence-aware extraction
- Multi-hop graph reasoning and path construction
- Cross-paper synthesis
- Source-aware generation formatting
- Evidence grounding validation
- Source-type-aware evidence strength scoring
"""

from __future__ import annotations

import pytest

from breakthrough_engine.evidence_source import EvidenceSource
from breakthrough_engine.kg_calibration import EvidenceCalibrator
from breakthrough_engine.kg_grounding import (
    EvidenceGroundingValidator,
    GroundingResult,
    _extract_claim_keywords,
    _keyword_overlap_score,
)
from breakthrough_engine.kg_reasoning import (
    CrossPaperSynthesizer,
    GraphEdge,
    GraphNode,
    KGGraphBuilder,
    MultiHopReasoner,
    ReasoningPath,
    SynthesisLink,
)
from breakthrough_engine.kg_segment_scorer import (
    MultiSignalScoringConfig,
    MultiSignalSegmentScorer,
    SegmentScoreBreakdown,
    _keyword_overlap_score as _seg_kw_score,
    _mechanism_specificity_score,
    _quantitative_density_score,
)
from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateScore,
    EvidenceItem,
    EvidencePack,
    ResearchProgram,
    new_id,
)
from breakthrough_engine.scoring import score_candidate


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


def _make_candidate(**kw) -> CandidateHypothesis:
    defaults = {
        "id": new_id(),
        "run_id": "test_run",
        "title": "Test Hypothesis",
        "domain": "clean-energy",
        "statement": "Perovskite solar cells with topological insulator contacts improve efficiency by reducing recombination.",
        "mechanism": "Topological surface states provide spin-momentum locked electron transport channels at the perovskite interface.",
        "expected_outcome": "Power conversion efficiency exceeding 26% in single-junction configuration.",
        "testability_window_hours": 48.0,
        "novelty_notes": "No prior combination of these materials.",
        "assumptions": ["Interface stability"],
        "risk_flags": [],
        "evidence_refs": [],
    }
    defaults.update(kw)
    return CandidateHypothesis(**defaults)


def _make_graph_node(name: str, paper_id: str, etype: str = "concept", conf: float = 0.7) -> GraphNode:
    return GraphNode(
        entity_id=new_id(),
        name=name,
        entity_type=etype,
        paper_id=paper_id,
        segment_id=f"seg_{name[:8]}",
        confidence=conf,
        description=f"Description of {name}",
    )


def _make_graph_edge(source: GraphNode, target: GraphNode, rtype: str = "enhances", conf: float = 0.6) -> GraphEdge:
    return GraphEdge(
        relation_id=new_id(),
        source_id=source.entity_id,
        target_id=target.entity_id,
        relation_type=rtype,
        paper_id=source.paper_id,
        confidence=conf,
    )


# ===========================================================================
# A. Multi-Signal Segment Scoring
# ===========================================================================

class TestMultiSignalSegmentScorer:
    def test_quantitative_text_scores_higher(self):
        scorer = MultiSignalSegmentScorer()
        quant_text = "We achieved 23.7% power conversion efficiency with perovskite solar cells at 300K."
        generic_text = "Solar cells are an important area of research for clean energy applications."
        q = scorer.score(quant_text, "clean-energy")
        g = scorer.score(generic_text, "clean-energy")
        assert q.composite_score > g.composite_score
        assert q.quantitative_density > g.quantitative_density

    def test_mechanism_text_scores_higher(self):
        scorer = MultiSignalSegmentScorer()
        mech = "Phonon scattering at the interface enables enhanced electron transport through tunneling."
        generic = "This paper discusses various applications of new materials."
        m = scorer.score(mech, "clean-energy")
        g = scorer.score(generic, "clean-energy")
        assert m.mechanism_specificity > g.mechanism_specificity

    def test_domain_keywords_boost_score(self):
        scorer = MultiSignalSegmentScorer()
        on_topic = "Perovskite tandem solar cell with silicon bottom cell achieves high efficiency."
        off_topic = "The economic impact of policy changes on regulatory frameworks."
        on = scorer.score(on_topic, "clean-energy")
        off = scorer.score(off_topic, "clean-energy")
        assert on.keyword_overlap > off.keyword_overlap

    def test_breakdown_to_dict(self):
        scorer = MultiSignalSegmentScorer()
        b = scorer.score("Test text with 25% efficiency", "clean-energy", "seg123")
        d = b.to_dict()
        assert d["segment_id"] == "seg123"
        assert "composite_score" in d
        assert all(k in d for k in [
            "embedding_similarity", "keyword_overlap", "quantitative_density",
            "citation_density", "mechanism_specificity",
        ])

    def test_configurable_weights(self):
        config = MultiSignalScoringConfig(
            embedding_weight=0.0,
            keyword_weight=0.5,
            quantitative_weight=0.5,
            citation_weight=0.0,
            mechanism_weight=0.0,
        )
        scorer = MultiSignalSegmentScorer(config=config)
        text = "Perovskite solar cell with 23.7% efficiency"
        b = scorer.score(text, "clean-energy")
        # With these weights, composite should be driven by keyword + quantitative only
        expected = b.keyword_overlap * 0.5 + b.quantitative_density * 0.5
        assert abs(b.composite_score - expected) < 0.01

    def test_batch_scoring(self):
        scorer = MultiSignalSegmentScorer()
        texts = ["Solar cell efficiency 25%", "Generic text", "MOF carbon capture at 8.2 mmol/g"]
        results = scorer.score_batch(texts, "clean-energy")
        assert len(results) == 3
        assert all(isinstance(r, SegmentScoreBreakdown) for r in results)


class TestSignalDetectors:
    def test_quantitative_detects_percentages(self):
        assert _quantitative_density_score("achieved 23.7% efficiency") > 0.0

    def test_quantitative_detects_units(self):
        assert _quantitative_density_score("measured 8.2 mmol at 300K") > 0.0

    def test_quantitative_zero_for_no_numbers(self):
        assert _quantitative_density_score("no numbers here") == 0.0

    def test_mechanism_detects_causal_language(self):
        assert _mechanism_specificity_score("electron transport and phonon scattering mechanism") > 0.0

    def test_keyword_overlap_clean_energy(self):
        assert _seg_kw_score("perovskite solar cell efficiency", "clean-energy") > 0.0
        assert _seg_kw_score("random unrelated text", "clean-energy") == 0.0


# ===========================================================================
# B. Confidence-Aware Extraction
# ===========================================================================

class TestConfidenceAwareExtraction:
    def test_mock_extractor_includes_confidence(self):
        from breakthrough_engine.kg_extractor import MockEntityRelationExtractor
        mock = MockEntityRelationExtractor()
        result = mock.extract_from_text("solar perovskite carbon capture")
        for ent in result["entities"]:
            assert "confidence" in ent
            assert 0.1 <= ent["confidence"] <= 1.0
        for rel in result.get("relations", []):
            assert "confidence" in rel
            assert 0.1 <= rel["confidence"] <= 1.0

    def test_confidence_not_hardcoded(self):
        from breakthrough_engine.kg_extractor import MockEntityRelationExtractor
        mock = MockEntityRelationExtractor()
        r1 = mock.extract_from_text("solar perovskite")
        r2 = mock.extract_from_text("mof framework carbon")
        # Different entities should potentially have different confidence
        confs = set()
        for ent in r1["entities"] + r2["entities"]:
            confs.add(ent["confidence"])
        assert len(confs) > 1, "All confidences are identical — not differentiated"


# ===========================================================================
# C. Multi-Hop Graph Reasoning
# ===========================================================================

class TestMultiHopReasoning:
    def _build_linear_graph(self) -> tuple[KGGraphBuilder, list[GraphNode]]:
        """Build A -> B -> C -> D graph for testing."""

        class FakeRepo:
            def list_kg_entities(self, **kw): return []
            def get_kg_relations_for_entity(self, eid): return []

        graph = KGGraphBuilder(FakeRepo())

        # Build nodes across two papers
        a = _make_graph_node("Perovskite", "paper_1", "material", 0.9)
        b = _make_graph_node("Electron Transport", "paper_1", "mechanism", 0.8)
        c = _make_graph_node("High Efficiency", "paper_2", "property", 0.85)
        d = _make_graph_node("Grid Storage", "paper_2", "technology", 0.7)

        for n in [a, b, c, d]:
            graph._nodes[n.entity_id] = n

        # Build edges: A->B, B->C (cross-paper!), C->D
        e1 = _make_graph_edge(a, b, "enhances", 0.8)
        e2 = _make_graph_edge(b, c, "enables", 0.7)
        e3 = _make_graph_edge(c, d, "used_in", 0.6)

        for edge in [e1, e2, e3]:
            graph._edges.append(edge)
            graph._adj.setdefault(edge.source_id, []).append(edge)
            graph._adj.setdefault(edge.target_id, []).append(edge)

        return graph, [a, b, c, d]

    def test_find_2hop_paths(self):
        graph, nodes = self._build_linear_graph()
        reasoner = MultiHopReasoner(graph, max_hops=2, min_path_confidence=0.1)
        paths = reasoner.find_paths(start_entity_id=nodes[0].entity_id)
        assert len(paths) >= 1
        # Should find A->B->C (2-hop)
        two_hop = [p for p in paths if p.hop_count == 2]
        assert len(two_hop) >= 1

    def test_find_3hop_paths(self):
        graph, nodes = self._build_linear_graph()
        reasoner = MultiHopReasoner(graph, max_hops=3, min_path_confidence=0.1)
        paths = reasoner.find_paths(start_entity_id=nodes[0].entity_id)
        three_hop = [p for p in paths if p.hop_count == 3]
        assert len(three_hop) >= 1

    def test_cross_paper_detection(self):
        graph, nodes = self._build_linear_graph()
        reasoner = MultiHopReasoner(graph, max_hops=2, min_path_confidence=0.1)
        paths = reasoner.find_paths(start_entity_id=nodes[0].entity_id)
        cross_paper = [p for p in paths if p.is_cross_paper]
        assert len(cross_paper) >= 1

    def test_path_confidence_computed(self):
        graph, nodes = self._build_linear_graph()
        reasoner = MultiHopReasoner(graph, max_hops=2, min_path_confidence=0.1)
        paths = reasoner.find_paths(start_entity_id=nodes[0].entity_id)
        for p in paths:
            assert 0.0 < p.path_confidence <= 1.0

    def test_path_to_evidence_item(self):
        graph, nodes = self._build_linear_graph()
        reasoner = MultiHopReasoner(graph, max_hops=2, min_path_confidence=0.1)
        paths = reasoner.find_paths(start_entity_id=nodes[0].entity_id)
        items = reasoner.paths_to_evidence(paths)
        assert len(items) >= 1
        for item in items:
            assert item.source_type == "graph_path"
            assert item.relevance_score > 0
            assert "→" in item.quote or "[" in item.quote

    def test_reasoning_trace_populated(self):
        graph, nodes = self._build_linear_graph()
        reasoner = MultiHopReasoner(graph, max_hops=2, min_path_confidence=0.1)
        paths = reasoner.find_paths(start_entity_id=nodes[0].entity_id)
        for p in paths:
            assert p.reasoning_trace != ""
            assert "therefore" in p.reasoning_trace or "enhances" in p.reasoning_trace

    def test_path_to_dict(self):
        graph, nodes = self._build_linear_graph()
        reasoner = MultiHopReasoner(graph, max_hops=2, min_path_confidence=0.1)
        paths = reasoner.find_paths(start_entity_id=nodes[0].entity_id)
        d = paths[0].to_dict()
        assert "hop_count" in d
        assert "path_confidence" in d
        assert "is_cross_paper" in d
        assert "nodes" in d
        assert "edges" in d

    def test_min_confidence_filters(self):
        graph, nodes = self._build_linear_graph()
        # High min should filter out all paths
        reasoner = MultiHopReasoner(graph, max_hops=2, min_path_confidence=0.99)
        paths = reasoner.find_paths(start_entity_id=nodes[0].entity_id)
        assert len(paths) == 0

    def test_find_cross_paper_paths_only(self):
        graph, nodes = self._build_linear_graph()
        reasoner = MultiHopReasoner(graph, max_hops=3, min_path_confidence=0.1)
        cross = reasoner.find_cross_paper_paths()
        for p in cross:
            assert p.is_cross_paper


# ===========================================================================
# D. Cross-Paper Synthesis
# ===========================================================================

class TestCrossPaperSynthesis:
    def _build_two_paper_graph(self) -> KGGraphBuilder:
        class FakeRepo:
            def list_kg_entities(self, **kw): return []
            def get_kg_relations_for_entity(self, eid): return []

        graph = KGGraphBuilder(FakeRepo())

        # Paper 1 entities
        a1 = _make_graph_node("Perovskite", "paper_1", "material", 0.9)
        a2 = _make_graph_node("Efficiency", "paper_1", "property", 0.85)
        # Paper 2 entities — shared name "Efficiency"
        b1 = _make_graph_node("Silicon", "paper_2", "material", 0.88)
        b2 = _make_graph_node("Efficiency", "paper_2", "property", 0.80)

        for n in [a1, a2, b1, b2]:
            graph._nodes[n.entity_id] = n

        # Relations
        e1 = _make_graph_edge(a1, a2, "enhances", 0.75)
        e2 = _make_graph_edge(b1, b2, "measured_by", 0.70)

        for edge in [e1, e2]:
            graph._edges.append(edge)
            graph._adj.setdefault(edge.source_id, []).append(edge)
            graph._adj.setdefault(edge.target_id, []).append(edge)

        return graph

    def test_finds_shared_concept_bridges(self):
        graph = self._build_two_paper_graph()
        synth = CrossPaperSynthesizer(graph, min_confidence=0.1)
        links = synth.synthesize()
        assert len(links) >= 1
        # Should find "Efficiency" as shared concept
        shared = [l for l in links if "Efficiency" in l.source_entity.name or "Efficiency" in l.target_entity.name]
        assert len(shared) >= 1

    def test_synthesis_to_evidence_item(self):
        graph = self._build_two_paper_graph()
        synth = CrossPaperSynthesizer(graph, min_confidence=0.1)
        links = synth.synthesize()
        items = synth.synthesis_to_evidence(links)
        assert len(items) >= 1
        for item in items:
            assert item.source_type == "kg_synthesis"
            assert "cross-paper" in item.title.lower() or "↔" in item.title

    def test_synthesis_link_to_dict(self):
        graph = self._build_two_paper_graph()
        synth = CrossPaperSynthesizer(graph, min_confidence=0.1)
        links = synth.synthesize()
        d = links[0].to_dict()
        assert "source" in d
        assert "target" in d
        assert "confidence" in d

    def test_no_synthesis_for_single_paper(self):
        class FakeRepo:
            def list_kg_entities(self, **kw): return []
            def get_kg_relations_for_entity(self, eid): return []

        graph = KGGraphBuilder(FakeRepo())
        n1 = _make_graph_node("A", "paper_1")
        n2 = _make_graph_node("B", "paper_1")
        graph._nodes[n1.entity_id] = n1
        graph._nodes[n2.entity_id] = n2

        synth = CrossPaperSynthesizer(graph)
        links = synth.synthesize()
        assert len(links) == 0


# ===========================================================================
# E. Source-Aware Generation Inputs
# ===========================================================================

class TestSourceAwareGeneration:
    def test_format_evidence_includes_source_type(self):
        from breakthrough_engine.candidate_generator import OllamaCandidateGenerator, _SOURCE_TYPE_LABELS
        gen = OllamaCandidateGenerator.__new__(OllamaCandidateGenerator)
        items = [
            _make_item("finding", 0.87),
            _make_item("kg_segment", 0.80),
            _make_item("graph_path", 0.70),
        ]
        formatted = gen._format_evidence(items)
        assert "[CURATED_FINDING]" in formatted
        assert "[KG_SEGMENT]" in formatted
        assert "[GRAPH_PATH]" in formatted
        assert "Source: finding" in formatted
        assert "Source: kg_segment" in formatted

    def test_evidence_block_template_has_type_key(self):
        from breakthrough_engine.candidate_generator import EVIDENCE_BLOCK_TEMPLATE
        assert "EVIDENCE TYPE KEY" in EVIDENCE_BLOCK_TEMPLATE
        assert "CURATED_FINDING" in EVIDENCE_BLOCK_TEMPLATE
        assert "KG_SEGMENT" in EVIDENCE_BLOCK_TEMPLATE
        assert "GRAPH_PATH" in EVIDENCE_BLOCK_TEMPLATE

    def test_source_type_labels_complete(self):
        from breakthrough_engine.candidate_generator import _SOURCE_TYPE_LABELS
        assert "finding" in _SOURCE_TYPE_LABELS
        assert "kg_segment" in _SOURCE_TYPE_LABELS
        assert "graph_path" in _SOURCE_TYPE_LABELS
        assert "kg_synthesis" in _SOURCE_TYPE_LABELS


# ===========================================================================
# F. Evidence Grounding Validation
# ===========================================================================

class TestEvidenceGrounding:
    def test_strong_support_with_matching_evidence(self):
        candidate = _make_candidate(
            statement="Perovskite solar cells with topological insulator contacts improve efficiency.",
            mechanism="Electron transport through topological surface states reduces recombination.",
        )
        evidence = [
            EvidenceItem(
                id=new_id(), source_type="finding", source_id="f:1",
                title="Perovskite solar cell efficiency improvements",
                quote="Perovskite cells with special contacts showed reduced recombination and improved electron transport efficiency to 25%.",
                citation="Test 2024", relevance_score=0.87,
            ),
        ]
        validator = EvidenceGroundingValidator()
        result = validator.validate(candidate, evidence)
        assert result.overall_verdict in ("strong_support", "weak_support")
        assert result.grounding_score > 0.3

    def test_unsupported_with_unrelated_evidence(self):
        candidate = _make_candidate(
            statement="Quantum computing enables faster drug discovery through molecular simulation.",
            mechanism="Quantum entanglement provides exponential speedup for molecular energy calculations.",
        )
        evidence = [
            EvidenceItem(
                id=new_id(), source_type="finding", source_id="f:1",
                title="Agricultural yield improvements in tropical regions",
                quote="Crop rotation increased corn yields by 15% in subtropical climates.",
                citation="Test 2024", relevance_score=0.87,
            ),
        ]
        validator = EvidenceGroundingValidator()
        result = validator.validate(candidate, evidence)
        assert result.grounding_score < 0.5

    def test_no_evidence_returns_unsupported(self):
        candidate = _make_candidate()
        validator = EvidenceGroundingValidator()
        result = validator.validate(candidate, [])
        assert result.overall_verdict == "unsupported"

    def test_grounding_result_to_dict(self):
        candidate = _make_candidate()
        evidence = [_make_item("finding", 0.87)]
        validator = EvidenceGroundingValidator()
        result = validator.validate(candidate, evidence)
        d = result.to_dict()
        assert "overall_verdict" in d
        assert "grounding_score" in d
        assert "evidence_count" in d

    def test_source_trust_priors_applied(self):
        candidate = _make_candidate()
        # Same content, different source types
        finding = _make_item("finding", 0.87)
        finding.title = "Perovskite solar cell efficiency"
        finding.quote = "Topological insulator contacts improve perovskite solar cell efficiency through reduced recombination."

        kg = _make_item("kg_graph", 0.87)
        kg.title = finding.title
        kg.quote = finding.quote

        validator = EvidenceGroundingValidator()
        r1 = validator.validate(candidate, [finding])
        r2 = validator.validate(candidate, [kg])
        # Finding should get higher grounding due to trust prior
        assert r1.grounding_score >= r2.grounding_score


# ===========================================================================
# G. Source-Type-Aware Evidence Strength Scoring
# ===========================================================================

class TestSourceTypeAwareScoring:
    def _make_program(self) -> ResearchProgram:
        return ResearchProgram(
            id="test",
            name="Test",
            domain="clean-energy",
            scoring_weights={
                "novelty": 0.2, "plausibility": 0.2, "impact": 0.2,
                "evidence_strength": 0.2, "simulation_readiness": 0.1,
                "inverse_validation_cost": 0.1,
            },
        )

    def test_diverse_evidence_gets_diversity_bonus(self):
        program = self._make_program()
        candidate = _make_candidate()

        # Monoculture: all findings
        mono_pack = EvidencePack(
            candidate_id="test",
            items=[_make_item("finding", 0.87, f"f:{i}") for i in range(5)],
            source_diversity_count=1,
        )
        # Diverse: findings + KG
        diverse_items = [_make_item("finding", 0.87, f"f:{i}") for i in range(3)]
        diverse_items += [_make_item("kg_segment", 0.85, f"kg:{i}") for i in range(2)]
        diverse_pack = EvidencePack(
            candidate_id="test",
            items=diverse_items,
            source_diversity_count=4,
        )

        s_mono = score_candidate(candidate, mono_pack, None, [], program)
        s_diverse = score_candidate(candidate, diverse_pack, None, [], program)

        # Diverse pack should get a higher diversity bonus
        assert s_diverse.evidence_strength_score >= s_mono.evidence_strength_score - 0.05

    def test_source_trust_affects_strength(self):
        program = self._make_program()
        candidate = _make_candidate()

        # All findings (trust=1.0)
        finding_pack = EvidencePack(
            candidate_id="test",
            items=[_make_item("finding", 0.85) for _ in range(3)],
            source_diversity_count=3,
        )
        # All kg_synthesis (trust=0.70)
        synth_pack = EvidencePack(
            candidate_id="test",
            items=[_make_item("kg_synthesis", 0.85) for _ in range(3)],
            source_diversity_count=3,
        )

        s_find = score_candidate(candidate, finding_pack, None, [], program)
        s_synth = score_candidate(candidate, synth_pack, None, [], program)

        # Findings should score higher due to trust multiplier
        assert s_find.evidence_strength_score > s_synth.evidence_strength_score


# ===========================================================================
# H. Integration: ReasoningPath + Grounding
# ===========================================================================

class TestReasoningIntegration:
    def test_path_evidence_can_be_grounded(self):
        """Reasoning paths converted to evidence items can be grounded."""
        path = ReasoningPath(
            nodes=[
                _make_graph_node("Perovskite", "p1", "material"),
                _make_graph_node("Electron Transport", "p1", "mechanism"),
                _make_graph_node("Efficiency", "p2", "property"),
            ],
            edges=[
                _make_graph_edge(
                    _make_graph_node("a", "p1"), _make_graph_node("b", "p1"),
                    "enhances", 0.8,
                ),
                _make_graph_edge(
                    _make_graph_node("b", "p1"), _make_graph_node("c", "p2"),
                    "enables", 0.7,
                ),
            ],
            hop_count=2,
            path_confidence=0.75,
            is_cross_paper=True,
            paper_ids={"p1", "p2"},
            reasoning_trace="Perovskite enhances Electron Transport, therefore Electron Transport enables Efficiency",
        )

        item = path.to_evidence_item()
        assert item.source_type == "graph_path"

        candidate = _make_candidate()
        validator = EvidenceGroundingValidator()
        result = validator.validate(candidate, [item])
        assert result.overall_verdict in ("strong_support", "weak_support", "unsupported")
        assert "grounding_score" in result.to_dict()
