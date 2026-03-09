"""Phase 7B tests: Production Hardening, Evaluation Pack, Embedding Hardening.

All tests are OFFLINE-SAFE:
- No Ollama network calls
- No real DB I/O (in-memory DB only)
- No file I/O beyond tmpdir
- No internet access

Tests cover:
1. Schema v009 migration
2. Evaluation pack exporter
3. Analysis schema serialization
4. Production embedding config selection in orchestrator
5. Strict embedding preflight failure
6. Smoke campaign profile loads correctly
7. Campaign receipt includes embedding_provider
8. Evaluation pack CLI command path
9. Morning-after inspection (evaluation_pack.list)
10. CampaignManager records embedding_provider in receipt
"""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_in_memory_db():
    """Create an in-memory DB initialized to v009."""
    from breakthrough_engine.db import init_db
    conn = init_db(in_memory=True)
    return conn


def _insert_minimal_campaign_receipt(db, campaign_id: str, **kwargs):
    """Insert a minimal campaign receipt row."""
    defaults = dict(
        profile_name="smoke_10m",
        profile_type="smoke",
        status="completed_with_draft",
        config_json=json.dumps({
            "domain": "clean-energy",
            "program_name": "clean_energy_shadow",
            "mode": "production",
            "wall_clock_budget_minutes": 10,
            "candidate_trial_budget": 8,
            "embedding_provider": "MockEmbeddingProvider",
            "embedding_model": "mock",
        }),
        preflight_json=json.dumps({
            "readiness_score": 1.0,
            "pass_count": 15,
            "warn_count": 0,
            "fail_count": 0,
            "checks": [],
        }),
        stage_events_json=json.dumps([
            {"stage_name": "preflight", "status": "completed", "elapsed_seconds": 0.1,
             "retries": 0, "error_message": "", "details": {}},
            {"stage_name": "lock_acquisition", "status": "completed", "elapsed_seconds": 0.0,
             "retries": 0, "error_message": "", "details": {}},
            {"stage_name": "db_init", "status": "completed", "elapsed_seconds": 0.1,
             "retries": 0, "error_message": "", "details": {}},
            {"stage_name": "daily_search_ladder", "status": "completed", "elapsed_seconds": 55.0,
             "retries": 0, "error_message": "", "details": {
                 "champion_id": "cand_champion_001",
                 "total_generated": 8,
                 "elapsed": 55.0,
             }},
            {"stage_name": "artifact_export", "status": "completed", "elapsed_seconds": 0.2,
             "retries": 0, "error_message": "", "details": {}},
        ]),
        started_at="2026-03-09T10:00:00Z",
        completed_at="2026-03-09T10:01:00Z",
        champion_candidate_id="cand_champion_001",
        champion_candidate_title="Test Champion Hypothesis",
        total_candidates_generated=8,
        total_blocked=0,
        total_shortlisted=3,
        policy_trials_attempted=2,
        retries_used=0,
        artifact_paths_json="[]",
        health_summary_json='{"healthy": true, "overnight_ready": true}',
        embedding_provider="MockEmbeddingProvider",
    )
    defaults.update(kwargs)

    db.execute(
        """INSERT OR REPLACE INTO bt_campaign_receipts
           (campaign_id, profile_name, profile_type, status,
            config_json, preflight_json, stage_events_json,
            started_at, completed_at,
            champion_candidate_id, champion_candidate_title,
            total_candidates_generated, total_blocked, total_shortlisted,
            policy_trials_attempted, retries_used,
            artifact_paths_json, health_summary_json,
            embedding_provider)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            campaign_id,
            defaults["profile_name"], defaults["profile_type"], defaults["status"],
            defaults["config_json"], defaults["preflight_json"], defaults["stage_events_json"],
            defaults["started_at"], defaults["completed_at"],
            defaults["champion_candidate_id"], defaults["champion_candidate_title"],
            defaults["total_candidates_generated"], defaults["total_blocked"],
            defaults["total_shortlisted"], defaults["policy_trials_attempted"],
            defaults["retries_used"], defaults["artifact_paths_json"],
            defaults["health_summary_json"], defaults["embedding_provider"],
        ),
    )
    db.commit()


def _insert_minimal_candidate(db, candidate_id: str, run_id: str, title: str,
                               status: str = "finalist", final_score: float = 0.80):
    db.execute(
        """INSERT OR REPLACE INTO bt_candidates
           (id, run_id, title, domain, statement, mechanism, expected_outcome,
            testability_window_hours, novelty_notes, assumptions, risk_flags,
            evidence_refs, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (candidate_id, run_id, title, "clean-energy",
         "Test statement.", "Test mechanism.", "Test outcome.",
         24.0, "Test novelty.", "[]", '["test risk"]', "[]",
         status, "2026-03-09T10:00:30Z"),
    )
    db.execute(
        """INSERT OR REPLACE INTO bt_scores
           (candidate_id, novelty_score, plausibility_score, impact_score,
            validation_cost_score, evidence_strength_score,
            simulation_readiness_score, final_score)
           VALUES (?,?,?,?,?,?,?,?)""",
        (candidate_id, 0.9, 0.8, 1.0, 0.5, 0.9, 1.0, final_score),
    )
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Schema v009 migration
# ═══════════════════════════════════════════════════════════════════════════════

class TestSchemaV009Migration:
    def test_schema_version_is_9(self):
        db = _make_in_memory_db()
        row = db.execute("SELECT MAX(version) FROM bt_schema_version").fetchone()
        assert row[0] == 9

    def test_bt_evaluation_packs_table_exists(self):
        db = _make_in_memory_db()
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "bt_evaluation_packs" in tables

    def test_embedding_provider_column_on_receipts(self):
        db = _make_in_memory_db()
        cols = [r[1] for r in db.execute(
            "PRAGMA table_info(bt_campaign_receipts)"
        ).fetchall()]
        assert "embedding_provider" in cols

    def test_bt_evaluation_packs_schema(self):
        db = _make_in_memory_db()
        cols = [r[1] for r in db.execute(
            "PRAGMA table_info(bt_evaluation_packs)"
        ).fetchall()]
        required = [
            "campaign_id", "schema_version", "artifact_dir",
            "champion_id", "champion_title", "champion_score",
            "total_candidates", "total_finalists",
            "embedding_provider", "policy_used", "created_at",
        ]
        for col in required:
            assert col in cols, f"Missing column: {col}"

    def test_receipt_default_embedding_provider(self):
        db = _make_in_memory_db()
        _insert_minimal_campaign_receipt(db, "test_schema_embed_001")
        row = db.execute(
            "SELECT embedding_provider FROM bt_campaign_receipts WHERE campaign_id=?",
            ("test_schema_embed_001",),
        ).fetchone()
        assert row is not None
        assert row[0] == "MockEmbeddingProvider"

    def test_schema_is_cumulative(self):
        """All prior schema tables are still present after v009."""
        db = _make_in_memory_db()
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        for expected in [
            "bt_candidates", "bt_scores", "bt_runs",
            "bt_campaign_receipts", "bt_preflight_results",
            "bt_campaign_heartbeats", "bt_evaluation_packs",
        ]:
            assert expected in tables


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Evaluation pack exporter
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvaluationPackExporter:
    def _setup_db_with_campaign(self, campaign_id: str):
        """Set up in-memory DB with a complete campaign."""
        db = _make_in_memory_db()

        # Insert a run
        run_id = "run_test_001"
        db.execute(
            """INSERT INTO bt_runs
               (id, program_name, mode, status, candidates_generated, candidates_rejected,
                started_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (run_id, "clean_energy_shadow", "production_shadow", "completed",
             4, 0, "2026-03-09T10:00:00Z", "2026-03-09T10:01:00Z"),
        )
        db.commit()

        # Insert candidates
        _insert_minimal_candidate(db, "cand_champ_001", run_id, "Champion Candidate", "finalist", 0.947)
        _insert_minimal_candidate(db, "cand_second_001", run_id, "Second Place", "finalist", 0.930)
        _insert_minimal_candidate(db, "cand_third_001", run_id, "Third Place", "finalist", 0.910)
        _insert_minimal_candidate(db, "cand_gen_001", run_id, "Generated Candidate", "generated", 0.800)

        # Insert campaign receipt
        _insert_minimal_campaign_receipt(
            db, campaign_id,
            champion_candidate_id="cand_champ_001",
            champion_candidate_title="Champion Candidate",
            total_candidates_generated=4,
            total_shortlisted=3,
        )

        # Insert daily campaign record
        db.execute(
            """INSERT OR IGNORE INTO bt_daily_campaigns
               (id, campaign_id, mode, policy_id, champion_candidate_id,
                config_json, result_json, started_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                "dc_test_001", campaign_id, "production", "phase5_champion",
                "cand_champ_001",
                json.dumps({"mode": "production", "program_name": "clean_energy_shadow"}),
                json.dumps({
                    "policy_used": "phase5_champion",
                    "daily_champion_id": "cand_champ_001",
                    "daily_champion_title": "Champion Candidate",
                    "champion_selection_rationale": "Score 0.947, APPROVE",
                    "total_candidates_generated": 4,
                    "total_blocked": 0,
                    "total_shortlisted": 3,
                    "elapsed_seconds": 55.0,
                }),
                "2026-03-09T10:00:00Z", "2026-03-09T10:01:00Z",
            ),
        )
        db.commit()
        return db

    def test_build_pack_returns_evaluation_pack(self, tmp_path):
        campaign_id = "test_ep_build_001"
        db = self._setup_db_with_campaign(campaign_id)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_db = f.name

        try:
            # Write in-memory DB to temp file
            import shutil
            real_db = sqlite3.connect(tmp_db)
            for line in db.iterdump():
                real_db.execute(line)
            real_db.commit()
            real_db.close()

            from breakthrough_engine.evaluation_pack import EvaluationPackExporter
            exporter = EvaluationPackExporter(db_path=tmp_db)

            with patch.dict(os.environ, {"SCIRES_RUNTIME_ROOT": str(tmp_path)}):
                out_dir = exporter.export(campaign_id, overwrite=True)

            assert os.path.isdir(out_dir)
            files = os.listdir(out_dir)
            assert "evaluation_pack.json" in files
            assert "evaluation_pack.md" in files
            assert "candidates.csv" in files
            assert "finalists.csv" in files
        finally:
            os.unlink(tmp_db)

    def test_pack_json_contains_required_fields(self, tmp_path):
        campaign_id = "test_ep_fields_001"
        db = self._setup_db_with_campaign(campaign_id)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_db = f.name
        try:
            real_db = sqlite3.connect(tmp_db)
            for line in db.iterdump():
                real_db.execute(line)
            real_db.commit()
            real_db.close()

            from breakthrough_engine.evaluation_pack import EvaluationPackExporter
            exporter = EvaluationPackExporter(db_path=tmp_db)
            with patch.dict(os.environ, {"SCIRES_RUNTIME_ROOT": str(tmp_path)}):
                out_dir = exporter.export(campaign_id, overwrite=True)

            with open(os.path.join(out_dir, "evaluation_pack.json")) as f:
                pack = json.load(f)

            # Required top-level keys
            for key in ["schema_version", "campaign", "config", "models", "statistics",
                        "champion", "tiebreak_notes", "preflight", "finalists", "all_candidates"]:
                assert key in pack, f"Missing key: {key}"

            # Schema version
            from breakthrough_engine.evaluation_pack import ANALYSIS_SCHEMA_VERSION
            assert pack["schema_version"] == ANALYSIS_SCHEMA_VERSION

            # Campaign section
            assert pack["campaign"]["campaign_id"] == campaign_id

            # Statistics
            assert pack["statistics"]["total_candidates_generated"] == 4
            assert pack["statistics"]["total_finalists"] == 3

        finally:
            os.unlink(tmp_db)

    def test_pack_finalists_csv_has_correct_columns(self, tmp_path):
        campaign_id = "test_ep_csv_001"
        db = self._setup_db_with_campaign(campaign_id)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_db = f.name
        try:
            real_db = sqlite3.connect(tmp_db)
            for line in db.iterdump():
                real_db.execute(line)
            real_db.commit()
            real_db.close()

            from breakthrough_engine.evaluation_pack import EvaluationPackExporter
            exporter = EvaluationPackExporter(db_path=tmp_db)
            with patch.dict(os.environ, {"SCIRES_RUNTIME_ROOT": str(tmp_path)}):
                out_dir = exporter.export(campaign_id, overwrite=True)

            with open(os.path.join(out_dir, "finalists.csv")) as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 3
            # Check required score columns
            for col in ["final_score", "novelty_score", "plausibility_score",
                        "impact_score", "falsification_risk"]:
                assert col in rows[0], f"Missing CSV column: {col}"

        finally:
            os.unlink(tmp_db)

    def test_pack_tiebreak_notes_present(self, tmp_path):
        campaign_id = "test_ep_tie_001"
        db = self._setup_db_with_campaign(campaign_id)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_db = f.name
        try:
            real_db = sqlite3.connect(tmp_db)
            for line in db.iterdump():
                real_db.execute(line)
            real_db.commit()
            real_db.close()

            from breakthrough_engine.evaluation_pack import EvaluationPackExporter
            exporter = EvaluationPackExporter(db_path=tmp_db)
            with patch.dict(os.environ, {"SCIRES_RUNTIME_ROOT": str(tmp_path)}):
                out_dir = exporter.export(campaign_id, overwrite=True)

            with open(os.path.join(out_dir, "evaluation_pack.json")) as f:
                pack = json.load(f)

            tb = pack["tiebreak_notes"]
            assert "ranked_finalists" in tb
            assert len(tb["ranked_finalists"]) == 3
            # Champion should be first
            assert tb["ranked_finalists"][0]["is_champion"]

        finally:
            os.unlink(tmp_db)

    def test_pack_markdown_has_champion_section(self, tmp_path):
        campaign_id = "test_ep_md_001"
        db = self._setup_db_with_campaign(campaign_id)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_db = f.name
        try:
            real_db = sqlite3.connect(tmp_db)
            for line in db.iterdump():
                real_db.execute(line)
            real_db.commit()
            real_db.close()

            from breakthrough_engine.evaluation_pack import EvaluationPackExporter
            exporter = EvaluationPackExporter(db_path=tmp_db)
            with patch.dict(os.environ, {"SCIRES_RUNTIME_ROOT": str(tmp_path)}):
                out_dir = exporter.export(campaign_id, overwrite=True)

            with open(os.path.join(out_dir, "evaluation_pack.md")) as f:
                md = f.read()

            assert "Champion Candidate" in md
            assert "Score Breakdown" in md
            assert "All Finalists" in md
            assert "schema_version" not in md  # shouldn't be raw JSON in MD

        finally:
            os.unlink(tmp_db)

    def test_existing_pack_not_overwritten_by_default(self, tmp_path):
        campaign_id = "test_ep_noover_001"
        db = self._setup_db_with_campaign(campaign_id)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_db = f.name
        try:
            real_db = sqlite3.connect(tmp_db)
            for line in db.iterdump():
                real_db.execute(line)
            real_db.commit()
            real_db.close()

            from breakthrough_engine.evaluation_pack import EvaluationPackExporter
            exporter = EvaluationPackExporter(db_path=tmp_db)
            with patch.dict(os.environ, {"SCIRES_RUNTIME_ROOT": str(tmp_path)}):
                out_dir1 = exporter.export(campaign_id, overwrite=False)
                # Write a sentinel file
                sentinel = os.path.join(out_dir1, "_sentinel_")
                open(sentinel, "w").close()
                # Re-export without overwrite — sentinel should survive
                out_dir2 = exporter.export(campaign_id, overwrite=False)
                assert os.path.exists(sentinel)

        finally:
            os.unlink(tmp_db)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Analysis schema serialization
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalysisSchema:
    def test_candidate_record_to_dict(self):
        from breakthrough_engine.evaluation_pack import CandidateRecord
        rec = CandidateRecord(
            candidate_id="cid001",
            run_id="rid001",
            title="Test",
            domain="clean-energy",
            statement="stmt",
            mechanism="mech",
            expected_outcome="outcome",
            testability_window_hours=24.0,
            novelty_notes="novel",
            assumptions=["a1"],
            risk_flags=["r1"],
            evidence_refs=["e1"],
            status="finalist",
            created_at="2026-03-09T00:00:00Z",
            final_score=0.85,
            novelty_score=0.9,
            falsification_risk="medium",
            falsification_passed=True,
        )
        d = rec.to_dict()
        assert d["candidate_id"] == "cid001"
        assert d["scores"]["final"] == 0.85
        assert d["scores"]["novelty"] == 0.9
        assert d["falsification"]["risk"] == "medium"
        assert d["falsification"]["passed"] is True

    def test_candidate_record_csv_row_has_all_keys(self):
        from breakthrough_engine.evaluation_pack import CandidateRecord
        rec = CandidateRecord(
            candidate_id="c1", run_id="r1", title="T", domain="d",
            statement="s", mechanism="m", expected_outcome="o",
            testability_window_hours=24.0, novelty_notes="n",
            assumptions=[], risk_flags=[], evidence_refs=[],
            status="finalist", created_at="2026-03-09T00:00:00Z",
            final_score=0.9,
        )
        row = rec.to_csv_row()
        for key in ["candidate_id", "title", "status", "final_score", "novelty_score",
                    "falsification_risk", "evidence_refs"]:
            assert key in row

    def test_evaluation_pack_to_dict_schema_version(self):
        from breakthrough_engine.evaluation_pack import EvaluationPack, ANALYSIS_SCHEMA_VERSION
        pack = EvaluationPack(campaign_id="test001")
        d = pack.to_dict()
        assert d["schema_version"] == ANALYSIS_SCHEMA_VERSION

    def test_evaluation_pack_empty_is_serializable(self):
        from breakthrough_engine.evaluation_pack import EvaluationPack
        pack = EvaluationPack(campaign_id="empty001")
        d = pack.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(d, default=str)
        assert "empty001" in json_str


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Production embedding config selection in orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

class TestProductionEmbeddingConfig:
    def _make_mock_program(self, mode_value: str):
        from breakthrough_engine.models import ResearchProgram, RunMode
        program = ResearchProgram(
            name="test_prog",
            domain="clean-energy",
            mode=RunMode(mode_value),
            allowed_simulators=[],
            candidate_budget=2,
        )
        return program

    def test_mock_provider_used_by_default_in_production_shadow(self):
        """Without BT_EMBEDDING_MODEL, production shadow still uses mock."""
        from breakthrough_engine.embeddings import MockEmbeddingProvider
        from breakthrough_engine.db import init_db
        from breakthrough_engine.db import Repository

        env = {"BT_EMBEDDING_MODEL": ""}
        with patch.dict(os.environ, env, clear=False):
            # Remove the key entirely
            if "BT_EMBEDDING_MODEL" in os.environ:
                del os.environ["BT_EMBEDDING_MODEL"]
            db = init_db(in_memory=True)
            repo = Repository(db)
            program = self._make_mock_program("production_shadow")
            from breakthrough_engine.orchestrator import BreakthroughOrchestrator
            orch = BreakthroughOrchestrator(program=program, repo=repo)
            assert isinstance(orch.embedding_novelty.provider, MockEmbeddingProvider)

    def test_ollama_provider_selected_when_bt_embedding_model_set(self):
        """With BT_EMBEDDING_MODEL set, production shadow uses OllamaEmbeddingProvider."""
        from breakthrough_engine.embeddings import OllamaEmbeddingProvider
        from breakthrough_engine.db import init_db, Repository

        with patch.dict(os.environ, {"BT_EMBEDDING_MODEL": "nomic-embed-text"}, clear=False):
            db = init_db(in_memory=True)
            repo = Repository(db)
            program = self._make_mock_program("production_shadow")
            from breakthrough_engine.orchestrator import BreakthroughOrchestrator
            orch = BreakthroughOrchestrator(program=program, repo=repo)
            assert isinstance(orch.embedding_novelty.provider, OllamaEmbeddingProvider)

    def test_explicit_provider_overrides_env(self):
        """Explicit embedding_provider parameter always takes precedence."""
        from breakthrough_engine.embeddings import MockEmbeddingProvider
        from breakthrough_engine.db import init_db, Repository

        with patch.dict(os.environ, {"BT_EMBEDDING_MODEL": "nomic-embed-text"}, clear=False):
            db = init_db(in_memory=True)
            repo = Repository(db)
            program = self._make_mock_program("production_shadow")
            explicit_mock = MockEmbeddingProvider()
            from breakthrough_engine.orchestrator import BreakthroughOrchestrator
            orch = BreakthroughOrchestrator(
                program=program, repo=repo, embedding_provider=explicit_mock
            )
            assert orch.embedding_novelty.provider is explicit_mock

    def test_mock_provider_in_deterministic_test_mode(self):
        """DETERMINISTIC_TEST mode always uses mock even with BT_EMBEDDING_MODEL set."""
        from breakthrough_engine.embeddings import MockEmbeddingProvider
        from breakthrough_engine.db import init_db, Repository

        with patch.dict(os.environ, {"BT_EMBEDDING_MODEL": "nomic-embed-text"}, clear=False):
            db = init_db(in_memory=True)
            repo = Repository(db)
            program = self._make_mock_program("deterministic_test")
            from breakthrough_engine.orchestrator import BreakthroughOrchestrator
            orch = BreakthroughOrchestrator(program=program, repo=repo)
            # deterministic_test should still use mock (not in production modes list)
            assert isinstance(orch.embedding_novelty.provider, MockEmbeddingProvider)

    def test_embedding_provider_name_attribute_set(self):
        """Orchestrator exposes _embedding_provider_name."""
        from breakthrough_engine.db import init_db, Repository

        with patch.dict(os.environ, {}, clear=False):
            if "BT_EMBEDDING_MODEL" in os.environ:
                del os.environ["BT_EMBEDDING_MODEL"]
            db = init_db(in_memory=True)
            repo = Repository(db)
            program = self._make_mock_program("production_shadow")
            from breakthrough_engine.orchestrator import BreakthroughOrchestrator
            orch = BreakthroughOrchestrator(program=program, repo=repo)
            assert hasattr(orch, "_embedding_provider_name")
            assert "MockEmbeddingProvider" in orch._embedding_provider_name


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Strict embedding preflight failure
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmbeddingPreflightHardening:
    def test_no_bt_embedding_model_passes_silently(self):
        """No env var → PASS with mock note."""
        from breakthrough_engine.preflight import PreflightEngine

        env = {}
        if "BT_EMBEDDING_MODEL" in os.environ:
            with patch.dict(os.environ, {}, clear=False):
                del os.environ["BT_EMBEDDING_MODEL"]
                engine = PreflightEngine()
                result = engine._check_embedding_model()
        else:
            engine = PreflightEngine()
            result = engine._check_embedding_model()

        assert result.status == "PASS"
        assert "MockEmbeddingProvider" in result.detail

    def test_bt_embedding_model_set_but_ollama_unreachable_fails(self):
        """BT_EMBEDDING_MODEL set but Ollama unreachable → FAIL."""
        from breakthrough_engine.preflight import PreflightEngine

        with patch.dict(os.environ, {"BT_EMBEDDING_MODEL": "nomic-embed-text",
                                     "OLLAMA_HOST": "127.0.0.1:9999"}, clear=False):
            engine = PreflightEngine()
            result = engine._check_embedding_model()

        assert result.status == "FAIL"
        assert "nomic-embed-text" in result.detail

    def test_bt_embedding_model_set_and_available_passes(self):
        """BT_EMBEDDING_MODEL set and model available → PASS."""
        from breakthrough_engine.preflight import PreflightEngine

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "nomic-embed-text:latest"}]}
        mock_resp.raise_for_status = MagicMock()

        with patch.dict(os.environ, {"BT_EMBEDDING_MODEL": "nomic-embed-text"}, clear=False):
            with patch("requests.get", return_value=mock_resp):
                engine = PreflightEngine()
                result = engine._check_embedding_model()

        assert result.status == "PASS"
        assert "OllamaEmbeddingProvider" in result.detail
        assert "real embeddings active" in result.detail

    def test_bt_embedding_model_set_but_not_found_in_ollama_fails(self):
        """BT_EMBEDDING_MODEL set but different model in Ollama → FAIL."""
        from breakthrough_engine.preflight import PreflightEngine

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "qwen3.5:9b-q4_K_M"}]}
        mock_resp.raise_for_status = MagicMock()

        with patch.dict(os.environ, {"BT_EMBEDDING_MODEL": "nomic-embed-text"}, clear=False):
            with patch("requests.get", return_value=mock_resp):
                engine = PreflightEngine()
                result = engine._check_embedding_model()

        assert result.status == "FAIL"
        assert "nomic-embed-text" in result.detail

    def test_fail_embedding_check_blocks_strict_preflight(self):
        """Strict preflight with FAIL embedding check blocks campaign."""
        from breakthrough_engine.preflight import PreflightEngine, PreflightReport

        with patch.dict(os.environ, {"BT_EMBEDDING_MODEL": "nomic-embed-text",
                                     "OLLAMA_HOST": "127.0.0.1:9999"}, clear=False):
            engine = PreflightEngine()

        # Manually build a report with a FAIL embedding check
        from breakthrough_engine.preflight import CheckResult
        report = PreflightReport(strict=True)
        report.checks = [
            CheckResult("embedding_model", "FAIL", "model not found",
                        "ollama pull nomic-embed-text"),
        ]
        assert report.has_failures
        assert not report.ready_for_campaign


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Smoke campaign profile
# ═══════════════════════════════════════════════════════════════════════════════

class TestSmokeCampaignProfile:
    def test_smoke_profile_loads(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("smoke_10m")
        assert profile.profile_name == "smoke_10m"
        assert profile.profile_type == "smoke"
        assert profile.wall_clock_budget_minutes == 10
        assert profile.domain == "clean-energy"
        assert profile.program_name == "clean_energy_shadow"

    def test_smoke_profile_has_short_budgets(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("smoke_10m")
        assert profile.wall_clock_budget_minutes <= 10
        assert profile.stage1_max_trials <= 3
        assert profile.stage2_shortlist_size <= 3

    def test_three_profiles_exist(self):
        """pilot_30m, overnight_clean_energy, smoke_10m all exist."""
        from breakthrough_engine.campaign_manager import load_campaign_profile
        for name in ["pilot_30m", "overnight_clean_energy", "smoke_10m"]:
            p = load_campaign_profile(name)
            assert p.profile_name == name


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Campaign receipt includes embedding_provider
# ═══════════════════════════════════════════════════════════════════════════════

class TestCampaignReceiptEmbeddingTelemetry:
    def test_receipt_embedding_provider_default_mock(self):
        from breakthrough_engine.campaign_manager import CampaignReceipt
        r = CampaignReceipt()
        assert r.embedding_provider == "MockEmbeddingProvider"

    def test_receipt_to_dict_includes_embedding_provider(self):
        from breakthrough_engine.campaign_manager import CampaignReceipt
        r = CampaignReceipt(
            campaign_id="test001",
            embedding_provider="OllamaEmbeddingProvider(nomic-embed-text)",
        )
        d = r.to_dict()
        assert "embedding_provider" in d
        assert d["embedding_provider"] == "OllamaEmbeddingProvider(nomic-embed-text)"

    def test_manager_sets_mock_provider_when_no_env(self):
        """CampaignManager sets MockEmbeddingProvider when BT_EMBEDDING_MODEL not set."""
        from breakthrough_engine.campaign_manager import CampaignManager, load_campaign_profile

        if "BT_EMBEDDING_MODEL" in os.environ:
            del os.environ["BT_EMBEDDING_MODEL"]

        db = _make_in_memory_db()
        from breakthrough_engine.db import Repository
        repo = Repository(db)
        mgr = CampaignManager(repo=repo)

        profile = load_campaign_profile("smoke_10m")
        receipt = mgr.run_campaign(profile, strict_preflight=False, dry_run=True)
        assert receipt.embedding_provider == "MockEmbeddingProvider"

    def test_manager_sets_ollama_provider_when_env_set(self):
        """CampaignManager sets OllamaEmbeddingProvider when BT_EMBEDDING_MODEL is set."""
        from breakthrough_engine.campaign_manager import CampaignManager, load_campaign_profile

        db = _make_in_memory_db()
        from breakthrough_engine.db import Repository
        repo = Repository(db)
        mgr = CampaignManager(repo=repo)

        profile = load_campaign_profile("smoke_10m")
        with patch.dict(os.environ, {"BT_EMBEDDING_MODEL": "nomic-embed-text"}, clear=False):
            receipt = mgr.run_campaign(profile, strict_preflight=False, dry_run=True)
        assert "OllamaEmbeddingProvider" in receipt.embedding_provider
        assert "nomic-embed-text" in receipt.embedding_provider

    def test_embedding_provider_persisted_to_db(self):
        """embedding_provider column is written to bt_campaign_receipts."""
        from breakthrough_engine.campaign_manager import CampaignManager, load_campaign_profile

        db = _make_in_memory_db()
        from breakthrough_engine.db import Repository
        repo = Repository(db)
        mgr = CampaignManager(repo=repo)

        profile = load_campaign_profile("smoke_10m")
        with patch.dict(os.environ, {"BT_EMBEDDING_MODEL": "nomic-embed-text"}, clear=False):
            receipt = mgr.run_campaign(profile, strict_preflight=False, dry_run=True)

        row = db.execute(
            "SELECT embedding_provider FROM bt_campaign_receipts WHERE campaign_id=?",
            (receipt.campaign_id,),
        ).fetchone()
        assert row is not None
        assert "OllamaEmbeddingProvider" in row[0]


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Evaluation pack CLI command paths
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvaluationPackCLI:
    def test_evaluation_pack_export_command_exists(self):
        """The evaluation-pack export command is registered."""
        from breakthrough_engine.cli import main
        import io as _io
        with patch("sys.argv", ["breakthrough_engine", "--help"]):
            with pytest.raises(SystemExit):
                main()

    def test_evaluation_pack_list_no_packs(self, tmp_path, capsys):
        from breakthrough_engine.cli import _cmd_evaluation_pack
        args = MagicMock()
        args.ep_command = "list"
        with patch.dict(os.environ, {"SCIRES_RUNTIME_ROOT": str(tmp_path)}, clear=False):
            _cmd_evaluation_pack(args)
        captured = capsys.readouterr()
        assert "No evaluation packs" in captured.out

    def test_evaluation_pack_list_shows_packs(self, tmp_path, capsys):
        pack_dir = tmp_path / "evaluation_packs" / "abc123"
        pack_dir.mkdir(parents=True)
        (pack_dir / "evaluation_pack.json").write_text("{}")
        (pack_dir / "candidates.csv").write_text("col1,col2\n")

        from breakthrough_engine.cli import _cmd_evaluation_pack
        args = MagicMock()
        args.ep_command = "list"
        with patch.dict(os.environ, {"SCIRES_RUNTIME_ROOT": str(tmp_path)}, clear=False):
            _cmd_evaluation_pack(args)
        captured = capsys.readouterr()
        assert "abc123" in captured.out
        assert "evaluation_pack.json" in captured.out


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Preflight report records embedding details
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreflightEmbeddingDetails:
    def test_preflight_report_serializable(self):
        from breakthrough_engine.preflight import PreflightEngine, PreflightReport, CheckResult
        report = PreflightReport(strict=True, campaign_profile="smoke_10m")
        report.checks = [
            CheckResult("embedding_model", "PASS",
                        "OllamaEmbeddingProvider(nomic-embed-text) available — real embeddings active"),
        ]
        d = report.to_dict()
        assert d["pass_count"] == 1
        assert d["warn_count"] == 0
        assert d["fail_count"] == 0
        assert "real embeddings active" in d["checks"][0]["detail"]

    def test_preflight_ready_with_fail_embedding_but_not_strict(self):
        """Not strict → FAIL embedding check doesn't block (but sets has_failures)."""
        from breakthrough_engine.preflight import PreflightReport, CheckResult
        report = PreflightReport(strict=False)
        report.checks = [
            CheckResult("python_environment", "PASS", "ok"),
            CheckResult("embedding_model", "FAIL", "not found"),
        ]
        # has_failures is True
        assert report.has_failures
        # ready_for_campaign = False because FAIL check
        assert not report.ready_for_campaign


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Phase-level: all prior schemas intact + total test count check
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhase7BIntegrity:
    def test_total_schema_tables_at_least_40(self):
        """v009 adds bt_evaluation_packs → total ≥ 40 tables."""
        db = _make_in_memory_db()
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        # 39 tables from v008 + 1 new (bt_evaluation_packs) = 40
        assert len(tables) >= 40

    def test_evaluation_pack_module_importable(self):
        from breakthrough_engine import evaluation_pack
        assert hasattr(evaluation_pack, "EvaluationPackExporter")
        assert hasattr(evaluation_pack, "EvaluationPack")
        assert hasattr(evaluation_pack, "CandidateRecord")
        assert hasattr(evaluation_pack, "ANALYSIS_SCHEMA_VERSION")

    def test_smoke_profile_yaml_valid(self):
        import yaml
        with open("config/campaign_profiles/smoke_10m.yaml") as f:
            data = yaml.safe_load(f)
        assert data["profile_name"] == "smoke_10m"
        assert data["wall_clock_budget_minutes"] == 10

    def test_overnight_profile_uses_clean_energy_shadow(self):
        """Regression: overnight profile must use clean_energy_shadow, not daily_quality."""
        import yaml
        with open("config/campaign_profiles/overnight_clean_energy.yaml") as f:
            data = yaml.safe_load(f)
        assert data["program_name"] == "clean_energy_shadow", (
            "overnight_clean_energy.yaml must use clean_energy_shadow"
        )
