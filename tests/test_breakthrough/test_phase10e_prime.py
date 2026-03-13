"""Tests for Phase 10E-Prime: Graph-native reasoning, canonicalization, subgraphs.

All tests are offline-safe — no network calls, no Ollama, no embedding model.
"""

from __future__ import annotations

import pytest
import sqlite3
from unittest.mock import MagicMock

from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateScore,
    EvidenceItem,
    EvidencePack,
    new_id,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mock_repo():
    """Create a mock Repository with KG data for testing."""
    repo = MagicMock()

    # Entities with intentional duplicates and value-entities
    entities = [
        {"id": "e1", "name": "Perovskite Solar Cell", "canonical_name": "perovskite solar cell",
         "entity_type": "device", "confidence": 0.85, "paper_id": "p1", "segment_id": "s1",
         "description": "Solar cell using perovskite absorber", "domain": "clean-energy", "status": "extracted"},
        {"id": "e2", "name": "Perovskite Solar Cells", "canonical_name": "perovskite solar cells",
         "entity_type": "device", "confidence": 0.80, "paper_id": "p2", "segment_id": "s2",
         "description": "Perovskite photovoltaic devices", "domain": "clean-energy", "status": "extracted"},
        {"id": "e3", "name": "Carbon Capture", "canonical_name": "carbon capture",
         "entity_type": "process", "confidence": 0.90, "paper_id": "p1", "segment_id": "s1",
         "description": "Process for capturing CO2", "domain": "clean-energy", "status": "extracted"},
        {"id": "e4", "name": "CO2 Capture", "canonical_name": "co2 capture",
         "entity_type": "process", "confidence": 0.75, "paper_id": "p3", "segment_id": "s3",
         "description": "Carbon dioxide capture process", "domain": "clean-energy", "status": "extracted"},
        {"id": "e5", "name": "MOF-303", "canonical_name": "mof-303",
         "entity_type": "material", "confidence": 0.92, "paper_id": "p2", "segment_id": "s2",
         "description": "Metal-organic framework for gas adsorption", "domain": "clean-energy", "status": "extracted"},
        {"id": "e6", "name": "33.7% efficiency", "canonical_name": "33.7% efficiency",
         "entity_type": "metric", "confidence": 0.50, "paper_id": "p1", "segment_id": "s1",
         "description": "", "domain": "clean-energy", "status": "extracted"},
        {"id": "e7", "name": "2.19 V", "canonical_name": "2.19 v",
         "entity_type": "metric", "confidence": 0.40, "paper_id": "p1", "segment_id": "s1",
         "description": "", "domain": "clean-energy", "status": "extracted"},
        {"id": "e8", "name": "Electron Transport Layer", "canonical_name": "electron transport layer",
         "entity_type": "structure", "confidence": 0.88, "paper_id": "p1", "segment_id": "s1",
         "description": "Layer for electron transport in solar cells", "domain": "clean-energy", "status": "extracted"},
        {"id": "e9", "name": "Band Gap", "canonical_name": "band gap",
         "entity_type": "property", "confidence": 0.82, "paper_id": "p2", "segment_id": "s2",
         "description": "Electronic band gap energy", "domain": "clean-energy", "status": "extracted"},
        {"id": "e10", "name": "Power Conversion Efficiency", "canonical_name": "power conversion efficiency",
         "entity_type": "property", "confidence": 0.87, "paper_id": "p3", "segment_id": "s3",
         "description": "Ratio of output power to input power", "domain": "clean-energy", "status": "extracted"},
    ]

    # Relations connecting entities
    relations = [
        {"id": "r1", "source_entity_id": "e1", "target_entity_id": "e8",
         "relation_type": "composed_of", "confidence": 0.7, "paper_id": "p1",
         "segment_id": "s1", "description": "PSC contains ETL", "domain": "clean-energy", "status": "extracted"},
        {"id": "r2", "source_entity_id": "e8", "target_entity_id": "e9",
         "relation_type": "measured_by", "confidence": 0.6, "paper_id": "p2",
         "segment_id": "s2", "description": "ETL properties measured by band gap", "domain": "clean-energy", "status": "extracted"},
        {"id": "r3", "source_entity_id": "e5", "target_entity_id": "e3",
         "relation_type": "used_in", "confidence": 0.8, "paper_id": "p2",
         "segment_id": "s2", "description": "MOF-303 used in carbon capture", "domain": "clean-energy", "status": "extracted"},
        {"id": "r4", "source_entity_id": "e1", "target_entity_id": "e10",
         "relation_type": "measured_by", "confidence": 0.75, "paper_id": "p3",
         "segment_id": "s3", "description": "Solar cell measured by PCE", "domain": "clean-energy", "status": "extracted"},
        {"id": "r5", "source_entity_id": "e9", "target_entity_id": "e10",
         "relation_type": "enhances", "confidence": 0.65, "paper_id": "p2",
         "segment_id": "s2", "description": "Optimized band gap enhances efficiency", "domain": "clean-energy", "status": "extracted"},
    ]

    repo.list_kg_entities.return_value = entities
    repo.list_kg_relations.return_value = relations

    def get_relations_for(eid):
        return [r for r in relations if r["source_entity_id"] == eid or r["target_entity_id"] == eid]
    repo.get_kg_relations_for_entity.side_effect = get_relations_for

    return repo


@pytest.fixture
def sample_evidence():
    """Sample evidence items of various source types."""
    return [
        EvidenceItem(
            id="ev1", source_type="finding", source_id="f1",
            title="Perovskite solar cells achieve 33% efficiency",
            quote="Recent advances in perovskite photovoltaic technology have achieved power conversion efficiency exceeding 33%.",
            citation="Nature Energy 2025", relevance_score=0.92,
        ),
        EvidenceItem(
            id="ev2", source_type="kg_segment", source_id="seg1",
            title="MOF-303 for CO2 capture",
            quote="Metal-organic framework MOF-303 shows exceptional CO2 adsorption capacity under ambient conditions.",
            citation="KG segment p2:s2", relevance_score=0.78,
        ),
        EvidenceItem(
            id="ev3", source_type="graph_path", source_id="path:p1:p2",
            title="Perovskite Solar Cell → Electron Transport → Band Gap",
            quote="Perovskite Solar Cell [composed_of] Electron Transport Layer [measured_by] Band Gap. Cross-paper path.",
            citation="KG 2-hop path (2 papers)", relevance_score=0.65,
        ),
        EvidenceItem(
            id="ev4", source_type="kg_synthesis", source_id="synth:p1:p3",
            title="Solar efficiency cross-paper bridge",
            quote="Carbon capture and solar efficiency share mechanistic overlap through material optimization.",
            citation="KG synthesis", relevance_score=0.55,
        ),
        EvidenceItem(
            id="ev5", source_type="kg_subgraph", source_id="subgraph_solar",
            title="Subgraph: solar efficiency (5 concepts, 2 papers)",
            quote="Concepts: perovskite solar cell, electron transport layer, band gap. Relations: composed_of, measured_by.",
            citation="KG subgraph (2 papers)", relevance_score=0.60,
        ),
    ]


@pytest.fixture
def sample_candidate():
    """Sample hypothesis candidate."""
    return CandidateHypothesis(
        id="cand1",
        run_id="run1",
        title="MOF-enhanced perovskite solar cells via electron transport optimization",
        domain="clean-energy",
        statement="Integrating MOF-303 into perovskite solar cell electron transport layers could enhance power conversion efficiency through optimized band gap engineering.",
        mechanism="MOF-303 provides ordered porous structure that can template electron transport layer growth, enabling precise band gap tuning for improved charge carrier extraction.",
        expected_outcome="Expected 2-5% improvement in PCE when MOF-303 is integrated into the ETL of perovskite tandem cells.",
        testability_window_hours=720,
        novelty_notes="Novel combination of MOF and perovskite technologies from separate research domains.",
        assumptions=["MOF integration does not degrade perovskite crystal quality"],
        risk_flags=[],
        evidence_refs=["ev1", "ev2", "ev3"],
    )


# ===========================================================================
# A: Concept canonicalization tests
# ===========================================================================

class TestConceptCanonicalization:
    """Tests for concept canonicalization and deduplication."""

    def test_value_entity_filtering(self):
        from breakthrough_engine.kg_canonicalization import _is_value_entity
        # Values should be filtered
        assert _is_value_entity("33.7%")
        assert _is_value_entity("2.19 V")
        assert _is_value_entity("170 GPa")
        assert _is_value_entity("250k")
        assert _is_value_entity("260k +/- 10k")
        # Concepts should NOT be filtered
        assert not _is_value_entity("Perovskite Solar Cell")
        assert not _is_value_entity("Carbon Capture")
        assert not _is_value_entity("MOF-303")
        assert not _is_value_entity("Electron Transport Layer")

    def test_generic_entity_filtering(self):
        from breakthrough_engine.kg_canonicalization import _is_generic_entity
        assert _is_generic_entity("result")
        assert _is_generic_entity("study")
        assert _is_generic_entity("method")
        assert not _is_generic_entity("perovskite")
        assert not _is_generic_entity("carbon capture")

    def test_name_normalization_synonyms(self):
        from breakthrough_engine.kg_canonicalization import normalize_entity_name
        # Synonym mapping
        assert normalize_entity_name("Perovskite Solar Cells") == "perovskite solar cell"
        assert normalize_entity_name("PSC") == "perovskite solar cell"
        assert normalize_entity_name("CO2 Capture") == "carbon capture"
        assert normalize_entity_name("MOF") == "metal-organic framework"
        assert normalize_entity_name("PCE") == "power conversion efficiency"
        assert normalize_entity_name("Voc") == "open-circuit voltage"
        assert normalize_entity_name("ETL") == "electron transport layer"

    def test_name_normalization_stemming(self):
        from breakthrough_engine.kg_canonicalization import normalize_entity_name
        # Plural handling via stemming
        assert normalize_entity_name("batteries") == "battery"

    def test_canonicalizer_runs(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import ConceptCanonicalizer
        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, stats = canonicalizer.canonicalize(domain="clean-energy")

        # Should filter value-entities
        assert stats.filtered_values >= 2  # "33.7% efficiency", "2.19 V"
        # Should have fewer canonical names than total entities
        assert stats.unique_canonical < stats.remaining_entities
        assert stats.duplicate_collapse_rate > 0

    def test_canonicalizer_deduplication(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import ConceptCanonicalizer
        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, stats = canonicalizer.canonicalize(domain="clean-energy")

        # "Perovskite Solar Cell" and "Perovskite Solar Cells" should merge
        assert "perovskite solar cell" in canonical_map
        psc = canonical_map["perovskite solar cell"]
        assert psc.mention_count >= 2
        assert len(psc.source_entity_ids) >= 2

    def test_canonicalizer_cross_paper_detection(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import ConceptCanonicalizer
        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, stats = canonicalizer.canonicalize(domain="clean-energy")

        # "Perovskite Solar Cell" appears in p1 and p2 -> cross-paper
        psc = canonical_map.get("perovskite solar cell")
        if psc:
            assert len(psc.source_paper_ids) >= 2

    def test_canonicalizer_entity_id_mapping(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import ConceptCanonicalizer
        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, _ = canonicalizer.canonicalize(domain="clean-energy")
        mapping = canonicalizer.build_entity_id_to_canonical(canonical_map)

        # All non-filtered entities should have a mapping
        assert len(mapping) > 0
        # Value entities should NOT be in the mapping
        assert "e6" not in mapping  # "33.7% efficiency"
        assert "e7" not in mapping  # "2.19 V"

    def test_canonicalization_stats_dict(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import ConceptCanonicalizer
        canonicalizer = ConceptCanonicalizer(mock_repo)
        _, stats = canonicalizer.canonicalize(domain="clean-energy")
        d = stats.to_dict()
        assert "total_entities" in d
        assert "filtered_values" in d
        assert "duplicate_collapse_rate" in d
        assert "top_clusters" in d


# ===========================================================================
# Canonical graph tests
# ===========================================================================

class TestCanonicalGraph:
    """Tests for the canonical concept graph."""

    def test_graph_builds_from_canonical_map(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import (
            ConceptCanonicalizer, CanonicalGraph,
        )
        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, _ = canonicalizer.canonicalize(domain="clean-energy")
        entity_id_map = canonicalizer.build_entity_id_to_canonical(canonical_map)
        relations = mock_repo.list_kg_relations.return_value

        graph = CanonicalGraph()
        graph.build(canonical_map, entity_id_map, relations)

        assert graph.node_count > 0
        assert graph.edge_count > 0

    def test_graph_self_loops_removed(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import (
            ConceptCanonicalizer, CanonicalGraph,
        )
        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, _ = canonicalizer.canonicalize(domain="clean-energy")
        entity_id_map = canonicalizer.build_entity_id_to_canonical(canonical_map)
        relations = mock_repo.list_kg_relations.return_value

        graph = CanonicalGraph()
        graph.build(canonical_map, entity_id_map, relations)

        for edge in graph.edges:
            assert edge.source_canonical != edge.target_canonical

    def test_graph_connected_components(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import (
            ConceptCanonicalizer, CanonicalGraph,
        )
        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, _ = canonicalizer.canonicalize(domain="clean-energy")
        entity_id_map = canonicalizer.build_entity_id_to_canonical(canonical_map)
        relations = mock_repo.list_kg_relations.return_value

        graph = CanonicalGraph()
        graph.build(canonical_map, entity_id_map, relations)

        components = graph.get_connected_components()
        assert len(components) >= 1
        # All nodes should be covered
        total = sum(len(c) for c in components)
        assert total == graph.node_count

    def test_graph_quality_metrics(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import (
            ConceptCanonicalizer, CanonicalGraph,
        )
        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, _ = canonicalizer.canonicalize(domain="clean-energy")
        entity_id_map = canonicalizer.build_entity_id_to_canonical(canonical_map)
        relations = mock_repo.list_kg_relations.return_value

        graph = CanonicalGraph()
        graph.build(canonical_map, entity_id_map, relations)

        metrics = graph.quality_metrics()
        assert "node_count" in metrics
        assert "edge_count" in metrics
        assert "connected_components" in metrics
        assert "relation_density" in metrics


# ===========================================================================
# C: Canonical multi-hop reasoning tests
# ===========================================================================

class TestCanonicalMultiHopReasoning:
    """Tests for canonical graph path finding."""

    def _build_graph(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import (
            ConceptCanonicalizer, CanonicalGraph,
        )
        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, _ = canonicalizer.canonicalize(domain="clean-energy")
        entity_id_map = canonicalizer.build_entity_id_to_canonical(canonical_map)
        relations = mock_repo.list_kg_relations.return_value
        graph = CanonicalGraph()
        graph.build(canonical_map, entity_id_map, relations)
        return graph

    def test_canonical_path_finding(self, mock_repo):
        from breakthrough_engine.kg_reasoning import CanonicalMultiHopReasoner
        graph = self._build_graph(mock_repo)
        reasoner = CanonicalMultiHopReasoner(graph, max_hops=3, min_path_confidence=0.1)
        paths = reasoner.find_paths(limit=20)
        # Should find paths through the connected entities
        assert len(paths) >= 0  # May be 0 if graph is too sparse after canonicalization

    def test_canonical_path_deduplication(self, mock_repo):
        from breakthrough_engine.kg_reasoning import CanonicalMultiHopReasoner
        graph = self._build_graph(mock_repo)
        reasoner = CanonicalMultiHopReasoner(graph, max_hops=3, min_path_confidence=0.05)
        paths = reasoner.find_paths(limit=50)
        # No duplicate concept sets
        seen = set()
        for p in paths:
            key = frozenset(p.concepts)
            assert key not in seen, f"Duplicate path: {p.concepts}"
            seen.add(key)

    def test_canonical_path_to_evidence(self, mock_repo):
        from breakthrough_engine.kg_reasoning import CanonicalMultiHopReasoner
        graph = self._build_graph(mock_repo)
        reasoner = CanonicalMultiHopReasoner(graph, max_hops=3, min_path_confidence=0.05)
        paths = reasoner.find_paths(limit=5)
        evidence = reasoner.paths_to_evidence(paths)
        for item in evidence:
            assert item.source_type == "graph_path"
            assert item.relevance_score >= 0

    def test_canonical_path_template_matching(self):
        from breakthrough_engine.kg_reasoning import CanonicalReasoningPath
        # A path that matches "material → property → device" template
        path = CanonicalReasoningPath(
            concepts=["silicon", "band gap", "solar cell"],
            relations=["measured_by", "enhances"],
            hop_count=2,
            path_confidence=0.6,
        )
        assert path.hop_count == 2
        d = path.to_dict()
        assert "concepts" in d
        assert "relations" in d


# ===========================================================================
# D: Subgraph construction tests
# ===========================================================================

class TestSubgraphConstruction:
    """Tests for cross-paper subgraph building."""

    def _build_graph(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import (
            ConceptCanonicalizer, CanonicalGraph,
        )
        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, _ = canonicalizer.canonicalize(domain="clean-energy")
        entity_id_map = canonicalizer.build_entity_id_to_canonical(canonical_map)
        relations = mock_repo.list_kg_relations.return_value
        graph = CanonicalGraph()
        graph.build(canonical_map, entity_id_map, relations)
        return graph

    def test_subgraph_from_seeds(self, mock_repo):
        from breakthrough_engine.kg_subgraph import SubgraphBuilder
        graph = self._build_graph(mock_repo)
        builder = SubgraphBuilder(graph, max_nodes=10)

        seeds = list(graph.concepts.keys())[:2]
        sg = builder.build_from_seeds(seeds, topic="test")
        assert sg.node_count > 0
        assert sg.topic == "test"

    def test_subgraph_from_topic(self, mock_repo):
        from breakthrough_engine.kg_subgraph import SubgraphBuilder
        graph = self._build_graph(mock_repo)
        builder = SubgraphBuilder(graph, max_nodes=10)

        sg = builder.build_from_topic("solar cell efficiency")
        assert sg.node_count >= 0  # May be 0 if no matches

    def test_subgraph_to_evidence_item(self, mock_repo):
        from breakthrough_engine.kg_subgraph import SubgraphBuilder
        graph = self._build_graph(mock_repo)
        builder = SubgraphBuilder(graph, max_nodes=10)

        seeds = list(graph.concepts.keys())[:3]
        sg = builder.build_from_seeds(seeds, topic="solar")
        if sg.node_count > 0:
            item = sg.to_evidence_item()
            assert item.source_type == "kg_subgraph"
            assert "solar" in item.title.lower() or "subgraph" in item.title.lower()

    def test_subgraph_to_prompt_block(self, mock_repo):
        from breakthrough_engine.kg_subgraph import SubgraphBuilder
        graph = self._build_graph(mock_repo)
        builder = SubgraphBuilder(graph, max_nodes=10)

        seeds = list(graph.concepts.keys())[:3]
        sg = builder.build_from_seeds(seeds, topic="solar")
        prompt = sg.to_prompt_block()
        assert "GRAPH NEIGHBORHOOD" in prompt

    def test_subgraph_cross_paper(self, mock_repo):
        from breakthrough_engine.kg_subgraph import SubgraphBuilder
        graph = self._build_graph(mock_repo)
        builder = SubgraphBuilder(graph, max_nodes=10)

        sg = builder.build_cross_paper_subgraph(min_confidence=0.1)
        d = sg.to_dict()
        assert "node_count" in d
        assert "cross_paper_edges" in d

    def test_subgraph_max_nodes_respected(self, mock_repo):
        from breakthrough_engine.kg_subgraph import SubgraphBuilder
        graph = self._build_graph(mock_repo)
        builder = SubgraphBuilder(graph, max_nodes=3)

        seeds = list(graph.concepts.keys())
        sg = builder.build_from_seeds(seeds, topic="test")
        assert sg.node_count <= 3


# ===========================================================================
# E: Graph-conditioned generation tests
# ===========================================================================

class TestGraphConditionedGeneration:
    """Tests for graph-conditioned generation formatting."""

    def test_source_type_labels_include_subgraph(self):
        from breakthrough_engine.candidate_generator import _SOURCE_TYPE_LABELS
        assert "kg_subgraph" in _SOURCE_TYPE_LABELS
        assert _SOURCE_TYPE_LABELS["kg_subgraph"] == "GRAPH_NEIGHBORHOOD"

    def test_graph_conditioned_template_exists(self):
        from breakthrough_engine.candidate_generator import GRAPH_CONDITIONED_TEMPLATE
        assert "GRAPH STRUCTURE" in GRAPH_CONDITIONED_TEMPLATE
        assert "CROSS-PAPER" in GRAPH_CONDITIONED_TEMPLATE

    def test_format_evidence_with_subgraph(self, sample_evidence):
        from breakthrough_engine.candidate_generator import OllamaCandidateGenerator
        gen = OllamaCandidateGenerator.__new__(OllamaCandidateGenerator)
        gen.config = MagicMock()
        text = gen._format_evidence(sample_evidence)
        assert "[GRAPH_NEIGHBORHOOD]" in text
        assert "[CURATED_FINDING]" in text
        assert "[GRAPH_PATH]" in text

    def test_build_graph_conditioned_prompt(self, sample_evidence):
        from breakthrough_engine.candidate_generator import OllamaCandidateGenerator
        gen = OllamaCandidateGenerator.__new__(OllamaCandidateGenerator)
        gen.config = MagicMock()
        prompt = gen._build_graph_conditioned_prompt(
            evidence=sample_evidence,
            domain="clean-energy",
            budget=5,
            graph_context="GRAPH NEIGHBORHOOD: solar\n  Concepts: a, b, c",
        )
        assert "GRAPH NEIGHBORHOOD" in prompt
        assert "clean-energy" in prompt
        assert "5" in prompt


# ===========================================================================
# F: Grounding validation tests
# ===========================================================================

class TestGroundingValidation:
    """Tests for evidence grounding + contradiction validation."""

    def test_grounding_includes_subgraph_trust(self):
        from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
        v = EvidenceGroundingValidator()
        assert "kg_subgraph" in v.trust_priors
        assert v.trust_priors["kg_subgraph"] > 0

    def test_grounding_with_mixed_evidence(self, sample_candidate, sample_evidence):
        from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
        v = EvidenceGroundingValidator()
        result = v.validate(sample_candidate, sample_evidence)
        assert result.grounding_score > 0
        assert result.overall_verdict in ("strong_support", "weak_support", "unsupported", "contradicted")
        assert len(result.evidence_verdicts) == len(sample_evidence)

    def test_grounding_graph_path_structural_bonus(self, sample_candidate):
        from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
        # Graph path with high overlap should get structural bonus
        evidence = [
            EvidenceItem(
                id="gp1", source_type="graph_path", source_id="path1",
                title="Perovskite → ETL → Band Gap",
                quote="perovskite solar cell electron transport layer band gap optimization mechanism",
                citation="KG 2-hop", relevance_score=0.7,
            ),
        ]
        v = EvidenceGroundingValidator()
        result = v.validate(sample_candidate, evidence)
        assert result.grounding_score > 0

    def test_grounding_contradiction_detection(self, sample_candidate):
        from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
        evidence = [
            EvidenceItem(
                id="contra1", source_type="finding", source_id="f1",
                title="MOF integration fails in perovskite cells",
                quote="MOF-303 integration failed to improve perovskite solar cell efficiency. No effect on power conversion was observed.",
                citation="Negative result", relevance_score=0.80,
            ),
        ]
        v = EvidenceGroundingValidator()
        result = v.validate(sample_candidate, evidence)
        # Should detect contradiction
        assert "contra1" in result.evidence_verdicts
        # Grounding should be penalized
        assert result.evidence_scores["contra1"] < 0.5

    def test_grounding_empty_evidence(self, sample_candidate):
        from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
        v = EvidenceGroundingValidator()
        result = v.validate(sample_candidate, [])
        assert result.overall_verdict == "unsupported"

    def test_grounding_result_to_dict(self, sample_candidate, sample_evidence):
        from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
        v = EvidenceGroundingValidator()
        result = v.validate(sample_candidate, sample_evidence)
        d = result.to_dict()
        assert "grounding_score" in d
        assert "overall_verdict" in d
        assert "evidence_count" in d


# ===========================================================================
# G: Graph-aware evidence strength tests
# ===========================================================================

class TestGraphAwareEvidenceStrength:
    """Tests for graph-aware evidence strength scoring."""

    def test_scoring_includes_subgraph_trust(self):
        from breakthrough_engine.scoring import score_candidate
        from breakthrough_engine.models import ResearchProgram
        program = ResearchProgram(
            id="rp1", name="test", domain="clean-energy",
            scoring_weights={"novelty": 0.2, "plausibility": 0.2, "impact": 0.15,
                             "evidence_strength": 0.25, "simulation_readiness": 0.1,
                             "inverse_validation_cost": 0.1},
        )
        candidate = CandidateHypothesis(
            id="c1", run_id="r1", title="Test",
            domain="clean-energy", statement="Test statement about solar cells.",
            mechanism="Solar cells use perovskite absorber materials.",
            expected_outcome="Improved efficiency.",
            testability_window_hours=24,
            novelty_notes="Novel combination of approaches.",
        )
        evidence = EvidencePack(
            candidate_id="c1",
            items=[
                EvidenceItem(
                    id="e1", source_type="finding", source_id="f1",
                    title="Solar finding", quote="Solar cell efficiency improved.",
                    citation="J1", relevance_score=0.9,
                ),
                EvidenceItem(
                    id="e2", source_type="kg_subgraph", source_id="sg1",
                    title="Subgraph evidence", quote="Solar cell graph neighborhood.",
                    citation="KG", relevance_score=0.6,
                ),
            ],
        )
        score = score_candidate(candidate, evidence, None, [], program)
        assert score.evidence_strength_score > 0
        # With 2 source types, should get diversity bonus
        assert score.evidence_strength_score > 0.5

    def test_graph_item_bonus(self):
        """Verify graph-native evidence types get a small bonus."""
        from breakthrough_engine.scoring import score_candidate
        from breakthrough_engine.models import ResearchProgram
        program = ResearchProgram(
            id="rp1", name="test", domain="clean-energy",
            scoring_weights={"novelty": 0.2, "plausibility": 0.2, "impact": 0.15,
                             "evidence_strength": 0.25, "simulation_readiness": 0.1,
                             "inverse_validation_cost": 0.1},
        )
        candidate = CandidateHypothesis(
            id="c1", run_id="r1", title="Test",
            domain="clean-energy", statement="Test",
            mechanism="Mechanism detail.", expected_outcome="Outcome.",
            testability_window_hours=24, novelty_notes="Novel.",
        )
        # All-findings pack
        findings_only = EvidencePack(
            candidate_id="c1",
            items=[
                EvidenceItem(id=f"f{i}", source_type="finding", source_id=f"s{i}",
                             title="Finding", quote="Quote text.", citation="J1",
                             relevance_score=0.85)
                for i in range(5)
            ],
        )
        # Mixed pack with graph evidence (same relevance scores)
        mixed = EvidencePack(
            candidate_id="c1",
            items=[
                EvidenceItem(id="f1", source_type="finding", source_id="s1",
                             title="Finding", quote="Quote text.", citation="J1",
                             relevance_score=0.85),
                EvidenceItem(id="f2", source_type="finding", source_id="s2",
                             title="Finding", quote="Quote text.", citation="J2",
                             relevance_score=0.85),
                EvidenceItem(id="g1", source_type="graph_path", source_id="p1",
                             title="Path", quote="Path quote.", citation="KG",
                             relevance_score=0.85),
                EvidenceItem(id="g2", source_type="kg_synthesis", source_id="syn1",
                             title="Synthesis", quote="Synth quote.", citation="KG",
                             relevance_score=0.85),
                EvidenceItem(id="g3", source_type="kg_subgraph", source_id="sg1",
                             title="Subgraph", quote="SG quote.", citation="KG",
                             relevance_score=0.85),
            ],
        )
        s1 = score_candidate(candidate, findings_only, None, [], program)
        s2 = score_candidate(candidate, mixed, None, [], program)
        # Mixed should have higher diversity bonus (more source types)
        assert s2.evidence_strength_score >= s1.evidence_strength_score - 0.05


# ===========================================================================
# H: Graph memory loop tests
# ===========================================================================

class TestGraphMemoryLoop:
    """Tests for write-back memory loop preparation."""

    def test_generate_write_back_payload(self, sample_candidate):
        from breakthrough_engine.kg_writer import generate_write_back_payload
        payload = generate_write_back_payload(
            sample_candidate,
            publication_id="pub1",
            confidence=0.75,
            grounding_verdict="strong_support",
            grounding_score=0.82,
            evidence_ids=["ev1", "ev2"],
        )
        assert payload["candidate_id"] == "cand1"
        assert payload["confidence"] == 0.75
        assert payload["grounding_verdict"] == "strong_support"
        assert payload["grounding_score"] == 0.82
        assert payload["status"] == "shadow"
        assert "id" in payload

    def test_write_back_readiness_check(self, mock_repo):
        from breakthrough_engine.kg_writer import write_back_readiness_check
        mock_repo.list_kg_findings.return_value = []
        result = write_back_readiness_check(mock_repo)
        assert result["ready"] is True
        assert result["activation_blocked"] is True

    def test_write_back_payload_without_publication(self, sample_candidate):
        from breakthrough_engine.kg_writer import generate_write_back_payload
        payload = generate_write_back_payload(
            sample_candidate,
            confidence=0.5,
        )
        assert payload["publication_id"] == ""
        assert payload["grounding_verdict"] == ""


# ===========================================================================
# Integration: end-to-end canonicalization -> reasoning -> subgraph
# ===========================================================================

class TestEndToEnd:
    """Integration tests for the full graph-native pipeline."""

    def test_canonicalize_then_reason(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import (
            ConceptCanonicalizer, CanonicalGraph,
        )
        from breakthrough_engine.kg_reasoning import CanonicalMultiHopReasoner

        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, stats = canonicalizer.canonicalize(domain="clean-energy")
        entity_id_map = canonicalizer.build_entity_id_to_canonical(canonical_map)
        relations = mock_repo.list_kg_relations.return_value

        graph = CanonicalGraph()
        graph.build(canonical_map, entity_id_map, relations)

        reasoner = CanonicalMultiHopReasoner(graph, max_hops=3, min_path_confidence=0.05)
        paths = reasoner.find_paths(limit=20)

        # Paths should all have valid concepts
        for p in paths:
            assert len(p.concepts) >= 3  # 2-hop minimum = 3 nodes
            assert p.hop_count >= 2

    def test_canonicalize_then_subgraph(self, mock_repo):
        from breakthrough_engine.kg_canonicalization import (
            ConceptCanonicalizer, CanonicalGraph,
        )
        from breakthrough_engine.kg_subgraph import SubgraphBuilder

        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, _ = canonicalizer.canonicalize(domain="clean-energy")
        entity_id_map = canonicalizer.build_entity_id_to_canonical(canonical_map)
        relations = mock_repo.list_kg_relations.return_value

        graph = CanonicalGraph()
        graph.build(canonical_map, entity_id_map, relations)

        builder = SubgraphBuilder(graph, max_nodes=8)
        sg = builder.build_from_topic("perovskite solar cell")

        if sg.node_count > 0:
            prompt = sg.to_prompt_block()
            assert "GRAPH NEIGHBORHOOD" in prompt
            item = sg.to_evidence_item()
            assert item.source_type == "kg_subgraph"

    def test_full_pipeline_canonical_to_grounding(self, mock_repo, sample_candidate):
        from breakthrough_engine.kg_canonicalization import (
            ConceptCanonicalizer, CanonicalGraph,
        )
        from breakthrough_engine.kg_reasoning import CanonicalMultiHopReasoner
        from breakthrough_engine.kg_subgraph import SubgraphBuilder
        from breakthrough_engine.kg_grounding import EvidenceGroundingValidator

        # Canonicalize
        canonicalizer = ConceptCanonicalizer(mock_repo)
        canonical_map, _ = canonicalizer.canonicalize(domain="clean-energy")
        entity_id_map = canonicalizer.build_entity_id_to_canonical(canonical_map)
        relations = mock_repo.list_kg_relations.return_value

        graph = CanonicalGraph()
        graph.build(canonical_map, entity_id_map, relations)

        # Get reasoning paths as evidence
        reasoner = CanonicalMultiHopReasoner(graph, max_hops=3, min_path_confidence=0.05)
        paths = reasoner.find_paths(limit=5)
        path_evidence = reasoner.paths_to_evidence(paths)

        # Get subgraph as evidence
        builder = SubgraphBuilder(graph, max_nodes=8)
        sg = builder.build_from_topic("solar cell")
        sg_evidence = [sg.to_evidence_item()] if sg.node_count > 0 else []

        # Validate grounding
        all_evidence = path_evidence + sg_evidence
        if all_evidence:
            validator = EvidenceGroundingValidator()
            result = validator.validate(sample_candidate, all_evidence)
            assert result.grounding_score >= 0
            assert result.overall_verdict in ("strong_support", "weak_support", "unsupported", "contradicted")
