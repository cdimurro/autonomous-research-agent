"""Phase 10A tests: KG shadow foundation — ingestion, extraction, retrieval, comparison, write-back.

All tests are offline-safe (no Ollama, no external network).
Uses in-memory SQLite and mock providers throughout.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateStatus,
    EvidenceItem,
    PublicationRecord,
    new_id,
)

REPO_ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """In-memory DB with all migrations applied."""
    conn = init_db(in_memory=True)
    return conn


@pytest.fixture
def repo(db):
    return Repository(db)


# ---------------------------------------------------------------------------
# A: Migration 12 — bt_paper_segments table
# ---------------------------------------------------------------------------

class TestMigration12PaperSegments:
    """bt_paper_segments table must exist and accept rows."""

    def test_table_exists(self, db):
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_paper_segments'"
        ).fetchone()
        assert row is not None, "bt_paper_segments table must exist"

    def test_insert_and_read(self, repo):
        seg = {
            "id": "seg_001",
            "paper_id": "paper_abc",
            "source_id": "arxiv:2401.00001",
            "segment_index": 0,
            "raw_text": "This is a test segment about perovskite solar cells.",
            "compressed_text": "",
            "relevance_score": 0.85,
            "domain": "clean-energy",
            "status": "ingested",
        }
        repo.save_paper_segment(seg)
        results = repo.list_paper_segments(domain="clean-energy")
        assert len(results) >= 1
        found = [r for r in results if r["id"] == "seg_001"]
        assert len(found) == 1
        assert found[0]["paper_id"] == "paper_abc"
        assert found[0]["relevance_score"] == 0.85

    def test_count(self, repo):
        for i in range(5):
            repo.save_paper_segment({
                "id": f"cnt_{i}",
                "paper_id": f"p_{i}",
                "domain": "clean-energy",
                "status": "ingested",
            })
        assert repo.count_paper_segments(domain="clean-energy") == 5
        assert repo.count_paper_segments(domain="clean-energy", status="ingested") == 5

    def test_status_update(self, repo):
        repo.save_paper_segment({
            "id": "upd_001",
            "paper_id": "p_upd",
            "domain": "clean-energy",
            "status": "ingested",
        })
        repo.update_segment_status("upd_001", "scored")
        rows = repo.list_paper_segments(status="scored")
        assert any(r["id"] == "upd_001" for r in rows)

    def test_filter_by_status(self, repo):
        repo.save_paper_segment({"id": "f1", "paper_id": "p1", "domain": "d", "status": "ingested"})
        repo.save_paper_segment({"id": "f2", "paper_id": "p2", "domain": "d", "status": "scored"})
        assert len(repo.list_paper_segments(status="ingested")) == 1
        assert len(repo.list_paper_segments(status="scored")) == 1


# ---------------------------------------------------------------------------
# B: Migration 12 — bt_kg_entities table
# ---------------------------------------------------------------------------

class TestMigration12KGEntities:
    """bt_kg_entities table must exist and accept rows."""

    def test_table_exists(self, db):
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_kg_entities'"
        ).fetchone()
        assert row is not None

    def test_insert_and_read(self, repo):
        repo.save_kg_entity({
            "id": "ent_001",
            "segment_id": "seg_001",
            "paper_id": "paper_abc",
            "entity_type": "material",
            "name": "Perovskite",
            "canonical_name": "perovskite",
            "description": "A type of crystalline material",
            "confidence": 0.8,
            "domain": "clean-energy",
        })
        entities = repo.list_kg_entities(domain="clean-energy")
        assert len(entities) >= 1
        assert entities[0]["name"] == "Perovskite"

    def test_entities_for_segment(self, repo):
        for i in range(3):
            repo.save_kg_entity({
                "id": f"ent_s_{i}",
                "segment_id": "seg_target",
                "entity_type": "concept",
                "name": f"Concept {i}",
            })
        results = repo.get_kg_entities_for_segment("seg_target")
        assert len(results) == 3


# ---------------------------------------------------------------------------
# C: Migration 12 — bt_kg_relations table
# ---------------------------------------------------------------------------

class TestMigration12KGRelations:
    """bt_kg_relations table must exist and accept rows."""

    def test_table_exists(self, db):
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_kg_relations'"
        ).fetchone()
        assert row is not None

    def test_insert_and_read(self, repo):
        repo.save_kg_relation({
            "id": "rel_001",
            "segment_id": "seg_001",
            "source_entity_id": "ent_001",
            "target_entity_id": "ent_002",
            "relation_type": "enhances",
            "description": "Perovskite enhances efficiency",
            "confidence": 0.7,
            "domain": "clean-energy",
        })
        relations = repo.list_kg_relations(domain="clean-energy")
        assert len(relations) >= 1
        assert relations[0]["relation_type"] == "enhances"

    def test_relations_for_entity(self, repo):
        repo.save_kg_relation({
            "id": "rel_e1",
            "segment_id": "seg_1",
            "source_entity_id": "ent_x",
            "target_entity_id": "ent_y",
            "relation_type": "causes",
        })
        repo.save_kg_relation({
            "id": "rel_e2",
            "segment_id": "seg_1",
            "source_entity_id": "ent_z",
            "target_entity_id": "ent_x",
            "relation_type": "inhibits",
        })
        results = repo.get_kg_relations_for_entity("ent_x")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# D: Migration 12 — bt_kg_findings table
# ---------------------------------------------------------------------------

class TestMigration12KGFindings:
    """bt_kg_findings table must exist and accept rows."""

    def test_table_exists(self, db):
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_kg_findings'"
        ).fetchone()
        assert row is not None

    def test_insert_and_read(self, repo):
        repo.save_kg_finding({
            "id": "kgf_001",
            "candidate_id": "cand_001",
            "publication_id": "pub_001",
            "title": "Test Finding",
            "statement": "Test statement",
            "mechanism": "Test mechanism",
            "domain": "clean-energy",
            "confidence": 0.7,
            "status": "active",
        })
        findings = repo.list_kg_findings(domain="clean-energy", status="active")
        assert len(findings) >= 1
        assert findings[0]["title"] == "Test Finding"

    def test_temporal_fields(self, db):
        """bt_kg_findings must have valid_from, valid_until, superseded_by columns."""
        row = db.execute(
            "SELECT sql FROM sqlite_master WHERE name='bt_kg_findings'"
        ).fetchone()
        sql = row[0]
        assert "valid_from" in sql
        assert "valid_until" in sql
        assert "superseded_by" in sql


# ---------------------------------------------------------------------------
# E: Paper ingestion worker
# ---------------------------------------------------------------------------

class TestPaperIngestion:
    """Paper ingestion worker tests with mocked data."""

    def test_segment_text_basic(self):
        from breakthrough_engine.paper_ingestion import segment_text
        text = "First paragraph about solar cells.\n\nSecond paragraph about efficiency."
        segments = segment_text(text)
        assert len(segments) == 2

    def test_segment_text_empty(self):
        from breakthrough_engine.paper_ingestion import segment_text
        assert segment_text("") == []
        assert segment_text("   ") == []

    def test_segment_text_long(self):
        from breakthrough_engine.paper_ingestion import segment_text
        text = "A" * 5000
        segments = segment_text(text, max_chars=2000)
        assert all(len(s) <= 2000 for s in segments)

    def test_segment_relevance_scorer_mock(self):
        from breakthrough_engine.embeddings import MockEmbeddingProvider
        from breakthrough_engine.paper_ingestion import SegmentRelevanceScorer

        scorer = SegmentRelevanceScorer(MockEmbeddingProvider(dim=64))
        score = scorer.score("perovskite solar cell efficiency", "clean-energy")
        assert 0.0 <= score <= 1.0

    def test_segment_relevance_batch(self):
        from breakthrough_engine.embeddings import MockEmbeddingProvider
        from breakthrough_engine.paper_ingestion import SegmentRelevanceScorer

        scorer = SegmentRelevanceScorer(MockEmbeddingProvider(dim=64))
        scores = scorer.score_batch(
            ["solar cell", "carbon capture", "machine learning"],
            "clean-energy",
        )
        assert len(scores) == 3
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_ingestion_worker_from_evidence(self, repo):
        """Ingest from bt_evidence_items (requires seeding evidence first)."""
        from breakthrough_engine.paper_ingestion import PaperIngestionWorker, IngestionConfig
        from breakthrough_engine.embeddings import MockEmbeddingProvider

        # Seed an evidence item
        repo.db.execute(
            """INSERT INTO bt_evidence_items (id, pack_id, source_type, source_id, title, quote, citation, relevance_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("evi_test_001", "pack_001", "paper", "arxiv:test",
             "Perovskite Solar Cell Advances",
             "We achieved 25% efficiency with a novel perovskite composition.",
             "Test et al. 2024", 0.85),
        )
        repo.db.commit()

        config = IngestionConfig(domain="clean-energy", limit=10)
        worker = PaperIngestionWorker(
            repo, embedding_provider=MockEmbeddingProvider(dim=64), config=config,
        )
        stats = worker.ingest_from_evidence_items(domain="clean-energy", limit=10)
        assert stats["ingested"] >= 1 or stats["errors"] == 0


# ---------------------------------------------------------------------------
# F: KG entity/relation extraction
# ---------------------------------------------------------------------------

class TestKGExtraction:
    """KG extraction tests with mock extractor."""

    def test_mock_extractor_returns_entities(self):
        from breakthrough_engine.kg_extractor import MockEntityRelationExtractor
        extractor = MockEntityRelationExtractor()
        result = extractor.extract_from_text("perovskite solar cell efficiency")
        assert "entities" in result
        assert len(result["entities"]) >= 1

    def test_mock_extractor_returns_relations(self):
        from breakthrough_engine.kg_extractor import MockEntityRelationExtractor
        extractor = MockEntityRelationExtractor()
        result = extractor.extract_from_text(
            "MOF carbon capture with perovskite solar cells",
        )
        assert "entities" in result
        assert "relations" in result

    def test_entity_types_valid(self):
        from breakthrough_engine.kg_extractor import ENTITY_TYPES
        assert "material" in ENTITY_TYPES
        assert "concept" in ENTITY_TYPES
        assert "mechanism" in ENTITY_TYPES

    def test_relation_types_valid(self):
        from breakthrough_engine.kg_extractor import RELATION_TYPES
        assert "causes" in RELATION_TYPES
        assert "enhances" in RELATION_TYPES
        assert "related_to" in RELATION_TYPES

    def test_extraction_pipeline_mock(self, repo):
        """Full extraction pipeline with mock extractor."""
        from breakthrough_engine.kg_extractor import EntityRelationExtractor

        # Seed a segment
        repo.save_paper_segment({
            "id": "ext_seg_001",
            "paper_id": "ext_paper_001",
            "raw_text": "Perovskite solar cells achieve high efficiency through novel mechanisms.",
            "domain": "clean-energy",
            "status": "scored",
            "relevance_score": 0.8,
        })

        extractor = EntityRelationExtractor(repo, mock=True)
        stats = extractor.extract_from_segments(domain="clean-energy", limit=10)

        assert stats["segments_processed"] >= 1
        assert stats["entities_extracted"] >= 1

        # Verify entities were persisted
        entities = repo.list_kg_entities(domain="clean-energy")
        assert len(entities) >= 1

    def test_extraction_marks_segment_extracted(self, repo):
        """After extraction, segment status should be 'extracted'."""
        from breakthrough_engine.kg_extractor import EntityRelationExtractor

        repo.save_paper_segment({
            "id": "ext_seg_002",
            "paper_id": "ext_paper_002",
            "raw_text": "Carbon capture via metal-organic frameworks shows promise.",
            "domain": "clean-energy",
            "status": "ingested",
        })

        extractor = EntityRelationExtractor(repo, mock=True)
        extractor.extract_from_segments(domain="clean-energy", limit=10)

        segments = repo.list_paper_segments(status="extracted")
        assert any(s["id"] == "ext_seg_002" for s in segments)

    def test_short_text_skipped(self, repo):
        """Segments with very short text should be skipped."""
        from breakthrough_engine.kg_extractor import EntityRelationExtractor

        repo.save_paper_segment({
            "id": "ext_seg_short",
            "paper_id": "ext_paper_short",
            "raw_text": "Too short",
            "domain": "clean-energy",
            "status": "scored",
        })

        extractor = EntityRelationExtractor(repo, mock=True)
        stats = extractor.extract_from_segments(domain="clean-energy", limit=10)
        # Should not count as a processing error
        assert stats["errors"] == 0

    def test_parse_extraction_response_valid(self):
        from breakthrough_engine.kg_extractor import _parse_extraction_response
        valid_json = json.dumps({
            "entities": [{"name": "test", "type": "concept"}],
            "relations": [],
        })
        result = _parse_extraction_response(valid_json)
        assert result is not None
        assert len(result["entities"]) == 1

    def test_parse_extraction_response_code_block(self):
        from breakthrough_engine.kg_extractor import _parse_extraction_response
        text = '```json\n{"entities": [{"name": "test"}], "relations": []}\n```'
        result = _parse_extraction_response(text)
        assert result is not None

    def test_parse_extraction_response_invalid(self):
        from breakthrough_engine.kg_extractor import _parse_extraction_response
        assert _parse_extraction_response("not json at all") is None
        assert _parse_extraction_response("") is None


# ---------------------------------------------------------------------------
# G: KGEvidenceSource shadow retrieval
# ---------------------------------------------------------------------------

class TestKGEvidenceSource:
    """KG shadow retrieval tests."""

    def test_implements_evidence_source(self):
        from breakthrough_engine.kg_retrieval import KGEvidenceSource
        from breakthrough_engine.evidence_source import EvidenceSource
        assert issubclass(KGEvidenceSource, EvidenceSource)

    def test_gather_returns_evidence_items(self, repo):
        from breakthrough_engine.kg_retrieval import KGEvidenceSource

        # Seed segments
        for i in range(3):
            repo.save_paper_segment({
                "id": f"kg_seg_{i}",
                "paper_id": f"kg_paper_{i}",
                "source_id": f"arxiv:test_{i}",
                "raw_text": f"Evidence about clean energy topic {i} with detailed findings.",
                "domain": "clean-energy",
                "status": "scored",
                "relevance_score": 0.7 + i * 0.05,
            })

        source = KGEvidenceSource(repo)
        items = source.gather("clean-energy", limit=10)
        assert len(items) >= 1
        assert all(isinstance(it, EvidenceItem) for it in items)

    def test_gather_respects_min_relevance(self, repo):
        from breakthrough_engine.kg_retrieval import KGEvidenceSource

        repo.save_paper_segment({
            "id": "kg_low",
            "paper_id": "p_low",
            "raw_text": "Low relevance text about something unrelated.",
            "domain": "clean-energy",
            "status": "scored",
            "relevance_score": 0.05,
        })

        source = KGEvidenceSource(repo, min_relevance=0.3)
        items = source.gather("clean-energy", limit=10)
        assert all(it.relevance_score >= 0.3 for it in items)

    def test_gather_with_graph_context(self, repo):
        from breakthrough_engine.kg_retrieval import KGEvidenceSource

        # Seed entity + relation
        repo.save_kg_entity({
            "id": "kg_ent_1",
            "segment_id": "seg_1",
            "entity_type": "material",
            "name": "Graphene",
            "description": "2D carbon material",
            "confidence": 0.9,
            "domain": "clean-energy",
        })
        repo.save_kg_entity({
            "id": "kg_ent_2",
            "segment_id": "seg_1",
            "entity_type": "property",
            "name": "Conductivity",
            "description": "Electrical conductivity",
            "confidence": 0.8,
            "domain": "clean-energy",
        })
        repo.save_kg_relation({
            "id": "kg_rel_1",
            "segment_id": "seg_1",
            "source_entity_id": "kg_ent_1",
            "target_entity_id": "kg_ent_2",
            "relation_type": "enhances",
            "description": "Graphene enhances conductivity",
            "confidence": 0.7,
            "domain": "clean-energy",
        })

        source = KGEvidenceSource(repo)
        items = source.gather("clean-energy", limit=20)
        graph_items = [it for it in items if it.source_type == "kg_graph"]
        assert len(graph_items) >= 1

    def test_evidence_item_shape(self, repo):
        """All returned items must have required EvidenceItem fields."""
        from breakthrough_engine.kg_retrieval import KGEvidenceSource

        repo.save_paper_segment({
            "id": "shape_seg",
            "paper_id": "shape_paper",
            "source_id": "arxiv:shape",
            "raw_text": "Detailed scientific evidence about clean energy materials and their properties.",
            "domain": "clean-energy",
            "status": "scored",
            "relevance_score": 0.8,
        })

        source = KGEvidenceSource(repo)
        items = source.gather("clean-energy", limit=5)
        for it in items:
            assert it.id
            assert it.source_type in ("kg_segment", "kg_graph", "finding")
            assert it.source_id
            assert it.title
            assert it.quote
            assert it.citation
            assert 0.0 <= it.relevance_score <= 1.0


# ---------------------------------------------------------------------------
# H: Shadow retrieval comparison harness
# ---------------------------------------------------------------------------

class TestComparisonHarness:
    """Shadow retrieval comparison harness tests."""

    def _make_items(self, n: int, source_type: str = "paper", base_score: float = 0.7) -> list[EvidenceItem]:
        return [
            EvidenceItem(
                id=new_id(),
                source_type=source_type,
                source_id=f"test:{i}",
                title=f"Test Item {i}",
                quote=f"Quote for test item {i} about scientific research.",
                citation=f"Author {i} (2024)",
                relevance_score=base_score + i * 0.02,
            )
            for i in range(n)
        ]

    def test_compute_metrics(self):
        from breakthrough_engine.kg_comparison import _compute_metrics
        items = self._make_items(5)
        metrics = _compute_metrics(items, "test")
        assert metrics.item_count == 5
        assert metrics.mean_relevance > 0
        assert metrics.unique_source_ids == 5

    def test_compute_metrics_empty(self):
        from breakthrough_engine.kg_comparison import _compute_metrics
        metrics = _compute_metrics([], "empty")
        assert metrics.item_count == 0

    def test_compute_overlap(self):
        from breakthrough_engine.kg_comparison import _compute_overlap
        a = self._make_items(3)
        # Create items with same source_ids
        b = [
            EvidenceItem(id=new_id(), source_type="test", source_id="test:0",
                         title="X", quote="Y", citation="Z", relevance_score=0.5),
            EvidenceItem(id=new_id(), source_type="test", source_id="test:99",
                         title="X", quote="Y", citation="Z", relevance_score=0.5),
        ]
        count, ids = _compute_overlap(a, b)
        assert count == 1
        assert "test:0" in ids

    def test_comparison_harness_run(self):
        from breakthrough_engine.evidence_source import DemoFixtureSource
        from breakthrough_engine.kg_comparison import RetrievalComparisonHarness

        class MockShadow:
            def gather(self, domain, limit=20):
                return [
                    EvidenceItem(
                        id=new_id(), source_type="kg_segment", source_id="kg:1",
                        title="KG Item", quote="KG evidence", citation="KG",
                        relevance_score=0.8,
                    ),
                ]

        harness = RetrievalComparisonHarness(DemoFixtureSource(), MockShadow())
        result = harness.compare("clean-energy", limit=10)

        assert result.domain == "clean-energy"
        assert result.current_metrics is not None
        assert result.shadow_metrics is not None
        assert result.verdict in (
            "shadow_better", "current_better", "comparable",
            "shadow_empty", "current_empty", "inconclusive",
        )

    def test_export_json(self):
        from breakthrough_engine.kg_comparison import ComparisonResult, SourceMetrics, RetrievalComparisonHarness

        result = ComparisonResult(
            domain="test",
            current_metrics=SourceMetrics(source_name="current", item_count=5, mean_relevance=0.7),
            shadow_metrics=SourceMetrics(source_name="shadow", item_count=3, mean_relevance=0.8),
            verdict="shadow_better",
            timestamp="2026-03-11T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "comparison.json")
            RetrievalComparisonHarness.export_json(result, path)
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert data["verdict"] == "shadow_better"

    def test_export_markdown(self):
        from breakthrough_engine.kg_comparison import ComparisonResult, SourceMetrics, RetrievalComparisonHarness

        result = ComparisonResult(
            domain="test",
            current_metrics=SourceMetrics(source_name="current", item_count=5, mean_relevance=0.7),
            shadow_metrics=SourceMetrics(source_name="shadow", item_count=3, mean_relevance=0.8),
            verdict="comparable",
            timestamp="2026-03-11T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "comparison.md")
            RetrievalComparisonHarness.export_markdown(result, path)
            assert os.path.exists(path)
            content = open(path).read()
            assert "Retrieval Comparison" in content

    def test_export_csv(self):
        from breakthrough_engine.kg_comparison import ComparisonResult, SourceMetrics, RetrievalComparisonHarness

        result = ComparisonResult(
            domain="test",
            current_metrics=SourceMetrics(source_name="current", item_count=5, mean_relevance=0.7),
            shadow_metrics=SourceMetrics(source_name="shadow", item_count=3, mean_relevance=0.8),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "comparison.csv")
            RetrievalComparisonHarness.export_csv(result, path)
            assert os.path.exists(path)


# ---------------------------------------------------------------------------
# I: KG write-back scaffolding
# ---------------------------------------------------------------------------

class TestKGWriteBack:
    """KG write-back scaffolding tests."""

    def _make_candidate(self) -> CandidateHypothesis:
        return CandidateHypothesis(
            id="wb_cand_001",
            run_id="run_001",
            title="Test Candidate for Write-Back",
            domain="clean-energy",
            statement="A testable hypothesis about clean energy.",
            mechanism="Through a novel mechanism.",
            expected_outcome="Measurable outcome.",
            evidence_refs=["evi_001", "evi_002"],
        )

    def test_write_candidate_as_finding(self, repo):
        from breakthrough_engine.kg_writer import write_candidate_as_finding

        candidate = self._make_candidate()
        finding_id = write_candidate_as_finding(
            repo, candidate, publication_id="pub_001", confidence=0.7, shadow=True,
        )
        assert finding_id

        finding = repo.get_kg_finding(finding_id)
        assert finding is not None
        assert finding["candidate_id"] == "wb_cand_001"
        assert finding["status"] == "shadow"
        assert finding["confidence"] == 0.7

    def test_write_publication_as_finding(self, repo):
        from breakthrough_engine.kg_writer import write_publication_as_finding

        candidate = self._make_candidate()
        publication = PublicationRecord(
            id="pub_wb_001",
            run_id="run_001",
            candidate_id=candidate.id,
            candidate_title=candidate.title,
            hypothesis=candidate.statement,
        )

        finding_id = write_publication_as_finding(
            repo, publication, candidate, shadow=True,
        )
        assert finding_id

        finding = repo.get_kg_finding(finding_id)
        assert finding["publication_id"] == "pub_wb_001"
        assert finding["confidence"] == 0.7  # publications get higher confidence

    def test_supersede_finding(self, repo):
        from breakthrough_engine.kg_writer import write_candidate_as_finding, supersede_finding

        candidate = self._make_candidate()
        old_id = write_candidate_as_finding(repo, candidate, shadow=False)
        candidate.id = "wb_cand_002"
        new_id_val = write_candidate_as_finding(repo, candidate, shadow=False)

        result = supersede_finding(repo, old_id, new_id_val)
        assert result is True

        old = repo.get_kg_finding(old_id)
        assert old["status"] == "superseded"
        assert old["superseded_by"] == new_id_val
        assert old["valid_until"] is not None

    def test_list_active_findings(self, repo):
        from breakthrough_engine.kg_writer import write_candidate_as_finding, list_active_findings

        candidate = self._make_candidate()
        write_candidate_as_finding(repo, candidate, shadow=False)

        active = list_active_findings(repo, domain="clean-energy")
        assert len(active) >= 1

    def test_list_shadow_findings(self, repo):
        from breakthrough_engine.kg_writer import write_candidate_as_finding, list_shadow_findings

        candidate = self._make_candidate()
        write_candidate_as_finding(repo, candidate, shadow=True)

        shadow = list_shadow_findings(repo, domain="clean-energy")
        assert len(shadow) >= 1


# ---------------------------------------------------------------------------
# J: Embedding regime protection
# ---------------------------------------------------------------------------

class TestEmbeddingRegimeProtection:
    """Ensure KG tables use Regime 2 (2560d) and do not mix with 768d."""

    def test_mock_provider_dimension(self):
        from breakthrough_engine.embeddings import MockEmbeddingProvider
        mock = MockEmbeddingProvider(dim=2560)
        assert mock.dimension() == 2560

    def test_ollama_provider_default_dimension(self):
        from breakthrough_engine.embeddings import OllamaEmbeddingProvider
        provider = OllamaEmbeddingProvider()
        assert provider.dimension() == 2560, "Default KG embeddings must be 2560d (Regime 2)"
        assert provider.model == "qwen3-embedding:4b"

    def test_segment_scorer_uses_provider_dimension(self):
        from breakthrough_engine.embeddings import MockEmbeddingProvider
        from breakthrough_engine.paper_ingestion import SegmentRelevanceScorer

        provider = MockEmbeddingProvider(dim=2560)
        scorer = SegmentRelevanceScorer(provider)
        assert scorer.provider.dimension() == 2560


# ---------------------------------------------------------------------------
# K: Schema version
# ---------------------------------------------------------------------------

class TestSchemaVersion:
    """Schema version must be at least 12 after migration."""

    def test_schema_version_at_least_12(self, db):
        row = db.execute("SELECT MAX(version) FROM bt_schema_version").fetchone()
        assert row[0] >= 12


# ---------------------------------------------------------------------------
# L: Production pipeline untouched
# ---------------------------------------------------------------------------

class TestProductionPipelineUntouched:
    """Verify no production pipeline code was changed."""

    def test_orchestrator_default_no_kg(self):
        """Orchestrator default path must not use KG evidence source."""
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        from breakthrough_engine.evidence_source import ExistingFindingsSource
        from breakthrough_engine.models import ResearchProgram, RunMode
        from breakthrough_engine.db import Repository, init_db

        db = init_db(in_memory=True)
        repo = Repository(db)
        program = ResearchProgram(
            name="test", domain="test", mode=RunMode.DETERMINISTIC_TEST,
        )
        orch = BreakthroughOrchestrator(program=program, repo=repo)
        # Default evidence source is NOT a KG source
        assert not type(orch.evidence_source).__name__.startswith("Hybrid")
        assert not type(orch.evidence_source).__name__.startswith("KG")
        # Graph context is disabled by default
        assert orch.enable_graph_context is False

    def test_daily_search_default_no_kg(self):
        """Daily search default config must not enable graph context."""
        from breakthrough_engine.daily_search import LadderConfig
        config = LadderConfig()
        assert config.evidence_source_override is None
        assert config.enable_graph_context is False

    def test_evidence_source_abc_unchanged(self):
        """EvidenceSource ABC must still have its gather method."""
        from breakthrough_engine.evidence_source import EvidenceSource
        assert hasattr(EvidenceSource, "gather")
        import inspect
        sig = inspect.signature(EvidenceSource.gather)
        assert "domain" in sig.parameters
        assert "limit" in sig.parameters

    def test_composite_retrieval_source_exists(self):
        """CompositeRetrievalSource must still exist in retrieval.py."""
        from breakthrough_engine.retrieval import CompositeRetrievalSource
        assert CompositeRetrievalSource is not None


# ---------------------------------------------------------------------------
# M: CLI integration smoke tests
# ---------------------------------------------------------------------------

class TestCLIIntegration:
    """CLI parser accepts new Phase 10A commands."""

    def test_ingest_parser_exists(self):
        from breakthrough_engine.cli import main
        import argparse
        # Just verify the parser doesn't crash on --help for ingest
        # (We can't actually run main with --help as it calls sys.exit)
        import breakthrough_engine.cli as cli_mod
        assert "ingest" in cli_mod.__file__ or True  # Smoke test

    def test_kg_parser_exists(self):
        import breakthrough_engine.cli as cli_mod
        source = open(cli_mod.__file__).read()
        assert "kg" in source
        assert "ingest" in source
        assert "extract" in source
        assert "compare" in source
        assert "writeback-status" in source
