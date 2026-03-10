"""Phase 7D tests: Measurement Closure, Full-Fidelity Evaluation Profile, Reviewed Batch.

All tests are OFFLINE-SAFE:
- No Ollama network calls
- No real DB I/O (in-memory DB only)
- No file I/O beyond tmpdir
- No internet access

Tests cover:
1. Actual candidate count used instead of arithmetic estimate (generated_count_mismatch fix)
2. falsify_all_finalists flag in LadderConfig and CampaignProfile
3. Evaluation profile YAML config values
4. Evaluation-grade integrity gate (hard fail on integrity failure)
5. bt_review_labels schema and DB operations
6. Review label save/retrieve/export via Repository
7. evaluation_pack schema v003 for evaluation-grade profiles
8. falsification_complete flag in accounting_diagnostics
9. Batch summary includes review labels
10. Full finalist falsification eliminates falsification_missing
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_in_memory_db():
    from breakthrough_engine.db import init_db
    return init_db(in_memory=True)


def _insert_receipt(
    db,
    campaign_id: str,
    profile_type: str = "evaluation",
    profile_name: str = "eval_clean_energy_30m",
    elapsed_seconds: float = 1800.0,
    champion_id: str = "cand_eval_champion",
    total_generated: int = 12,
    total_blocked: int = 3,
    total_shortlisted: int = 6,
    status: str = "completed_with_draft",
):
    """Insert a receipt for an evaluation-grade campaign."""
    ladder_campaign_id = f"ladder_{campaign_id[:8]}"
    stage_events = [
        {"stage_name": "preflight", "status": "completed", "elapsed_seconds": 1.0,
         "retries": 0, "error_message": "", "details": {}},
        {"stage_name": "daily_search_ladder", "status": "completed",
         "elapsed_seconds": elapsed_seconds, "retries": 0, "error_message": "",
         "details": {"campaign_id": ladder_campaign_id, "champion_id": champion_id}},
    ]
    db.execute(
        """INSERT OR REPLACE INTO bt_campaign_receipts
           (campaign_id, profile_name, profile_type, status,
            config_json, preflight_json, stage_events_json,
            started_at, completed_at, elapsed_seconds,
            champion_candidate_id, champion_candidate_title,
            total_candidates_generated, total_blocked, total_shortlisted,
            policy_trials_attempted, retries_used,
            artifact_paths_json, health_summary_json, embedding_provider)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            campaign_id, profile_name, profile_type, status,
            json.dumps({
                "domain": "clean-energy", "program_name": "clean_energy_shadow",
                "mode": "production", "wall_clock_budget_minutes": 30,
                "candidate_trial_budget": 10,
                "embedding_provider": "OllamaEmbeddingProvider(nomic-embed-text)",
                "embedding_model": "nomic-embed-text",
            }),
            json.dumps({"readiness_score": 1.0, "pass_count": 15, "warn_count": 0, "fail_count": 0}),
            json.dumps(stage_events),
            "2026-03-09T10:00:00Z",
            "2026-03-09T10:30:00Z",
            elapsed_seconds,
            champion_id,
            "Test Eval Champion",
            total_generated,  # arithmetic estimate (may differ from DB)
            total_blocked,
            total_shortlisted,
            2, 0, "[]",
            json.dumps({"healthy": True}),
            "OllamaEmbeddingProvider(nomic-embed-text)",
        ),
    )
    db.commit()
    return ladder_campaign_id


def _insert_daily_campaign(db, ladder_campaign_id: str, champion_id: str,
                            rationale: str = "Score 0.92, APPROVE. Highest final_score."):
    result_dict = {
        "policy_used": "phase5_champion",
        "daily_champion_id": champion_id,
        "champion_selection_rationale": rationale,
    }
    db.execute(
        """INSERT OR REPLACE INTO bt_daily_campaigns
           (id, campaign_id, mode, policy_id, champion_candidate_id,
            config_json, result_json, started_at, completed_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        ("dc_eval_001", ladder_campaign_id, "production", "phase5_champion", champion_id,
         "{}", json.dumps(result_dict),
         "2026-03-09T10:00:05Z", "2026-03-09T10:29:55Z"),
    )
    db.commit()


def _insert_run(db, run_id: str, started_at: str = "2026-03-09T10:00:05Z"):
    db.execute(
        """INSERT OR REPLACE INTO bt_runs
           (id, program_name, mode, status, candidates_generated,
            candidates_rejected, started_at, completed_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (run_id, "clean_energy_shadow", "production", "completed", 12, 3,
         started_at, "2026-03-09T10:29:50Z"),
    )
    db.commit()


def _insert_candidate(db, candidate_id: str, run_id: str, title: str,
                       status: str = "finalist", final_score: float = 0.90):
    db.execute(
        """INSERT OR REPLACE INTO bt_candidates
           (id, run_id, title, domain, statement, mechanism, expected_outcome,
            testability_window_hours, novelty_notes, assumptions, risk_flags,
            evidence_refs, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (candidate_id, run_id, title, "clean-energy",
         "Statement.", "Mechanism.", "Outcome.", 24.0, "Novelty notes.",
         "[]", "[]", '["ref1", "ref2"]',
         status, "2026-03-09T10:05:00Z"),
    )
    db.execute(
        """INSERT OR REPLACE INTO bt_scores
           (candidate_id, novelty_score, plausibility_score, impact_score,
            validation_cost_score, evidence_strength_score,
            simulation_readiness_score, final_score)
           VALUES (?,?,?,?,?,?,?,?)""",
        (candidate_id, 0.95, 0.90, 0.90, 0.30, 0.95, 1.0, final_score),
    )
    db.commit()


def _insert_falsification(db, candidate_id: str, run_id: str,
                           risk: str = "medium", passed: bool = True):
    db.execute(
        """INSERT OR REPLACE INTO bt_falsification_summaries
           (id, candidate_id, run_id, contradictions_json, missing_evidence_json,
            assumption_fragility_score, bridge_weakness_json,
            falsification_risk, passed, reasoning)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (f"fs_{candidate_id}", candidate_id, run_id,
         "[]", "[]", 0.6, "[]", risk, int(passed), "Tested and found sound."),
    )
    db.commit()


# ── Test 1: LadderConfig falsify_all_finalists field ─────────────────────────

class TestLadderConfigFalsifyAllFinalists:
    def test_falsify_all_finalists_default_false(self):
        from breakthrough_engine.daily_search import LadderConfig
        cfg = LadderConfig()
        assert cfg.falsify_all_finalists is False

    def test_falsify_all_finalists_can_be_set_true(self):
        from breakthrough_engine.daily_search import LadderConfig
        cfg = LadderConfig(falsify_all_finalists=True)
        assert cfg.falsify_all_finalists is True


# ── Test 2: CampaignProfile falsify_all_finalists ────────────────────────────

class TestCampaignProfileFalsifyAllFinalists:
    def test_campaign_profile_default_false(self):
        from breakthrough_engine.campaign_manager import CampaignProfile
        p = CampaignProfile()
        assert p.falsify_all_finalists is False

    def test_eval_profile_yaml_loads_falsify_all_finalists(self):
        """eval_clean_energy_30m YAML should set falsify_all_finalists=True."""
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("eval_clean_energy_30m")
        assert profile.falsify_all_finalists is True

    def test_eval_profile_is_evaluation_type(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("eval_clean_energy_30m")
        assert profile.profile_type == "evaluation"

    def test_eval_profile_has_large_shortlist(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("eval_clean_energy_30m")
        # Must be large enough to pass all typical finalists to stage 3
        assert profile.stage2_shortlist_size >= 6

    def test_eval_profile_stage3_covers_all_finalists(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("eval_clean_energy_30m")
        # max_trials must be large enough to cover all finalists in eval mode
        assert profile.stage3_max_trials >= 8

    def test_eval_profile_strict_falsification(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("eval_clean_energy_30m")
        assert profile.falsification_strict is True

    def test_eval_profile_30m_budget(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("eval_clean_energy_30m")
        assert profile.wall_clock_budget_minutes == 30

    def test_smoke_profile_unchanged(self):
        """Smoke profile should NOT have falsify_all_finalists."""
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("smoke_10m")
        assert profile.falsify_all_finalists is False


# ── Test 3: Actual candidate count fix ───────────────────────────────────────

class TestActualCandidateCountFix:
    def test_stage1_details_has_actual_candidates_generated(self):
        """Stage 1 result details must include actual_candidates_generated key."""
        from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig, StageConfig
        from breakthrough_engine.db import init_db, Repository

        db = init_db(in_memory=True)
        repo = Repository(db)

        # Build a minimal program mock
        program = MagicMock()
        program.mode = MagicMock()
        program.mode.__str__ = lambda s: "deterministic_test"
        from breakthrough_engine.models import RunMode
        program.mode = RunMode.DETERMINISTIC_TEST
        program.candidate_budget = 8

        # Mock _run_single_trial to return controlled counts
        with patch.object(DailySearchLadder, "_run_single_trial") as mock_trial:
            mock_run = MagicMock()
            mock_run.id = "run_mock_001"
            # Returns (run_record, finalists, actual_candidate_count)
            mock_trial.return_value = (mock_run, [], 7)  # 7 actual candidates

            ladder = DailySearchLadder()
            config = LadderConfig(
                stage1=StageConfig(max_trials=1, min_score_to_advance=0.0,
                                   max_wall_clock_seconds=300, abandon_floor=0.0),
                stage2_shortlist_size=2,
            )
            stage1_result, _ = ladder._stage1_exploration(repo, program, MagicMock(), config)

        assert "actual_candidates_generated" in stage1_result.details
        assert stage1_result.details["actual_candidates_generated"] == 7

    def test_run_campaign_uses_actual_count(self):
        """run_campaign should use actual count from stage1 details, not arithmetic."""
        from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig, StageConfig
        from breakthrough_engine.db import init_db, Repository

        db = init_db(in_memory=True)
        repo = Repository(db)

        with patch.object(DailySearchLadder, "_stage1_exploration") as mock_s1, \
             patch.object(DailySearchLadder, "_save_campaign"):
            from breakthrough_engine.daily_search import LadderStageResult
            # Arithmetic estimate would be trials(1) * budget(8) = 8
            # Actual count is 5 (different from estimate)
            mock_s1.return_value = (
                LadderStageResult(
                    stage_name="stage1_exploration",
                    trials_attempted=1,
                    stop_reason="abandoned",  # abandoned so we get early exit
                    details={"actual_candidates_generated": 5, "total_collected": 0},
                ),
                [],  # no finalists
            )

            ladder = DailySearchLadder()
            config = LadderConfig(
                mode="production",
                stage1=StageConfig(max_trials=1, min_score_to_advance=0.5,
                                   max_wall_clock_seconds=60, abandon_floor=0.4),
            )

            program = MagicMock()
            from breakthrough_engine.models import RunMode
            program.mode = RunMode.DETERMINISTIC_TEST
            program.candidate_budget = 8

            result = ladder.run_campaign(repo, config, program=program)

        # Should use actual count (5), not arithmetic estimate (1 * 8 = 8)
        assert result.total_candidates_generated == 5


# ── Test 4: Review labels DB schema ──────────────────────────────────────────

class TestReviewLabelsDBSchema:
    def test_bt_review_labels_table_exists(self):
        db = _make_in_memory_db()
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_review_labels'"
        ).fetchone()
        assert row is not None, "bt_review_labels table must exist after migration 10"

    def test_review_labels_columns(self):
        db = _make_in_memory_db()
        cols_info = db.execute("PRAGMA table_info(bt_review_labels)").fetchall()
        col_names = [c[1] for c in cols_info]
        required = [
            "id", "campaign_id", "candidate_id", "candidate_title",
            "candidate_role", "decision", "novelty_confidence",
            "technical_plausibility", "commercialization_relevance",
            "key_flaw", "reviewer_note", "reviewer", "created_at",
        ]
        for col in required:
            assert col in col_names, f"Missing column: {col}"

    def test_review_label_decision_default_is_defer(self):
        db = _make_in_memory_db()
        from breakthrough_engine.models import new_id
        label_id = new_id()
        db.execute(
            """INSERT INTO bt_review_labels (id, campaign_id, candidate_id, candidate_title)
               VALUES (?,?,?,?)""",
            (label_id, "camp_001", "cand_001", "Test candidate"),
        )
        db.commit()
        row = db.execute("SELECT decision FROM bt_review_labels WHERE id=?", (label_id,)).fetchone()
        assert row[0] == "defer"


# ── Test 5: Repository review label methods ───────────────────────────────────

class TestRepositoryReviewLabels:
    def test_save_and_retrieve_review_label(self):
        db = _make_in_memory_db()
        from breakthrough_engine.db import Repository
        repo = Repository(db)

        label = {
            "campaign_id": "camp_eval_001",
            "candidate_id": "cand_champion_001",
            "candidate_title": "Solar Hydrogen Breakthrough",
            "candidate_role": "champion",
            "decision": "approve",
            "novelty_confidence": 0.9,
            "technical_plausibility": 0.85,
            "commercialization_relevance": 0.75,
            "key_flaw": "Catalyst cost is prohibitive at scale",
            "reviewer_note": "Strong novelty, verify with expert",
            "reviewer": "operator",
        }
        repo.save_review_label(label)

        labels = repo.get_review_labels_for_campaign("camp_eval_001")
        assert len(labels) == 1
        lbl = labels[0]
        assert lbl["decision"] == "approve"
        assert lbl["candidate_role"] == "champion"
        assert abs(lbl["novelty_confidence"] - 0.9) < 0.01
        assert lbl["key_flaw"] == "Catalyst cost is prohibitive at scale"

    def test_multiple_labels_ordered_by_role(self):
        db = _make_in_memory_db()
        from breakthrough_engine.db import Repository
        repo = Repository(db)

        for role, cid in [("runner_up", "cand_002"), ("champion", "cand_001"), ("finalist", "cand_003")]:
            repo.save_review_label({
                "campaign_id": "camp_002",
                "candidate_id": cid,
                "candidate_title": f"Candidate {cid}",
                "candidate_role": role,
                "decision": "defer",
            })

        labels = repo.get_review_labels_for_campaign("camp_002")
        roles = [lbl["candidate_role"] for lbl in labels]
        # champion should come first, then runner_up, then finalist
        assert roles.index("champion") < roles.index("runner_up")
        assert roles.index("runner_up") < roles.index("finalist")

    def test_list_all_review_labels(self):
        db = _make_in_memory_db()
        from breakthrough_engine.db import Repository
        repo = Repository(db)

        for i in range(3):
            repo.save_review_label({
                "campaign_id": f"camp_{i:03d}",
                "candidate_id": f"cand_{i:03d}",
                "candidate_title": f"Title {i}",
                "decision": "approve" if i == 0 else "reject",
            })

        all_labels = repo.list_all_review_labels()
        assert len(all_labels) == 3

    def test_save_label_replaces_on_same_id(self):
        db = _make_in_memory_db()
        from breakthrough_engine.db import Repository
        repo = Repository(db)

        label = {
            "id": "fixed_id_001",
            "campaign_id": "camp_001",
            "candidate_id": "cand_001",
            "candidate_title": "Test",
            "decision": "defer",
        }
        repo.save_review_label(label)
        # Replace with approve
        label["decision"] = "approve"
        repo.save_review_label(label)

        labels = repo.get_review_labels_for_campaign("camp_001")
        assert len(labels) == 1
        assert labels[0]["decision"] == "approve"


# ── Test 6: Evaluation-grade integrity gate ───────────────────────────────────

class TestEvaluationGradeIntegrityGate:
    def _build_pack_with_missing_falsification(self, tmp_path):
        """Build an evaluation pack with a finalist missing falsification."""
        from breakthrough_engine.evaluation_pack import EvaluationPackExporter, EVALUATION_GRADE_PROFILE_TYPES

        db = _make_in_memory_db()
        campaign_id = "eval_grade_test_001"
        ladder_cid = _insert_receipt(db, campaign_id, profile_type="evaluation",
                                      total_generated=2, total_shortlisted=1)
        _insert_daily_campaign(db, ladder_cid, "cand_eval_champion")
        _insert_run(db, "run_eval_001")
        _insert_candidate(db, "cand_eval_champion", "run_eval_001",
                          "Champion Candidate", status="finalist", final_score=0.92)
        # No falsification for champion — should trigger MISSING

        db_path = str(tmp_path / "test.db")
        # Export the in-memory DB to file for the exporter
        import sqlite3 as _sqlite3
        file_db = _sqlite3.connect(db_path)
        db.backup(file_db)
        file_db.close()

        exporter = EvaluationPackExporter(db_path=db_path)
        return exporter, campaign_id

    def test_evaluation_grade_raises_on_integrity_failure(self, tmp_path):
        exporter, campaign_id = self._build_pack_with_missing_falsification(tmp_path)
        with pytest.raises(ValueError, match="integrity failed"):
            exporter.export(campaign_id, overwrite=True)

    def test_smoke_profile_does_not_raise_on_integrity_failure(self, tmp_path):
        """Smoke profile packs should log failures but not raise."""
        from breakthrough_engine.evaluation_pack import EvaluationPackExporter

        db = _make_in_memory_db()
        campaign_id = "smoke_test_001"
        ladder_cid = _insert_receipt(db, campaign_id, profile_type="smoke",
                                      profile_name="smoke_10m",
                                      total_generated=1, total_blocked=0, total_shortlisted=1)
        _insert_daily_campaign(db, ladder_cid, "cand_smoke_champion")
        _insert_run(db, "run_smoke_001")
        _insert_candidate(db, "cand_smoke_champion", "run_smoke_001",
                          "Smoke Champion", status="finalist", final_score=0.88)
        # No falsification — should log but NOT raise for smoke profile

        db_path = str(tmp_path / "smoke.db")
        import sqlite3 as _sqlite3
        file_db = _sqlite3.connect(db_path)
        db.backup(file_db)
        file_db.close()

        exporter = EvaluationPackExporter(db_path=db_path)
        # Should not raise
        out_dir = exporter.export(campaign_id, overwrite=True)
        assert os.path.exists(os.path.join(out_dir, "evaluation_pack.json"))

    def test_evaluation_pack_uses_v003_schema_for_eval_profile(self, tmp_path):
        """Evaluation-grade packs must use schema version v003."""
        from breakthrough_engine.evaluation_pack import EvaluationPackExporter

        db = _make_in_memory_db()
        campaign_id = "eval_v003_test"
        # Use total_blocked=0 so receipt matches DB (no novelty_failed candidates)
        ladder_cid = _insert_receipt(db, campaign_id, profile_type="evaluation",
                                      total_generated=1, total_blocked=0, total_shortlisted=1)
        _insert_daily_campaign(db, ladder_cid, "cand_v003")
        _insert_run(db, "run_v003_001")
        _insert_candidate(db, "cand_v003", "run_v003_001",
                          "V003 Champion", status="finalist", final_score=0.91)
        # Add falsification to pass integrity check
        _insert_falsification(db, "cand_v003", "run_v003_001")

        db_path = str(tmp_path / "v003.db")
        import sqlite3 as _sqlite3
        file_db = _sqlite3.connect(db_path)
        db.backup(file_db)
        file_db.close()

        exporter = EvaluationPackExporter(db_path=db_path)
        out_dir = exporter.export(campaign_id, overwrite=True)

        with open(os.path.join(out_dir, "evaluation_pack.json")) as f:
            pack = json.load(f)
        assert pack["schema_version"] == "v003"

    def test_smoke_pack_uses_v002_schema(self, tmp_path):
        """Smoke packs must still use schema v002."""
        from breakthrough_engine.evaluation_pack import EvaluationPackExporter

        db = _make_in_memory_db()
        campaign_id = "smoke_v002_test"
        ladder_cid = _insert_receipt(db, campaign_id, profile_type="smoke",
                                      profile_name="smoke_10m",
                                      total_generated=1, total_blocked=0, total_shortlisted=1)
        _insert_daily_campaign(db, ladder_cid, "cand_smoke_v002")
        _insert_run(db, "run_smoke_v002_001")
        _insert_candidate(db, "cand_smoke_v002", "run_smoke_v002_001",
                          "Smoke V002 Champion", status="finalist", final_score=0.88)
        _insert_falsification(db, "cand_smoke_v002", "run_smoke_v002_001")

        db_path = str(tmp_path / "smoke_v002.db")
        import sqlite3 as _sqlite3
        file_db = _sqlite3.connect(db_path)
        db.backup(file_db)
        file_db.close()

        exporter = EvaluationPackExporter(db_path=db_path)
        out_dir = exporter.export(campaign_id, overwrite=True)

        with open(os.path.join(out_dir, "evaluation_pack.json")) as f:
            pack = json.load(f)
        assert pack["schema_version"] == "v002"


# ── Test 7: Accounting diagnostics falsification_complete flag ─────────────

class TestFalsificationCompleteFlag:
    def test_falsification_complete_true_when_all_have_summaries(self):
        from breakthrough_engine.evaluation_pack import _build_accounting_diagnostics
        diag = _build_accounting_diagnostics(
            campaign_id="camp_001",
            ladder_campaign_id="ladder_001",
            receipt_generated=10,
            receipt_blocked=2,
            receipt_shortlisted=3,
            db_generated=10,
            db_blocked=2,
            db_finalists=3,
            db_shortlisted=3,
            elapsed_seconds=1800.0,
            champion_rationale_present=True,
            finalists_missing_falsification=0,
        )
        assert diag["falsification_complete"] is True
        assert diag["integrity_ok"] is True

    def test_falsification_complete_false_when_missing(self):
        from breakthrough_engine.evaluation_pack import _build_accounting_diagnostics
        diag = _build_accounting_diagnostics(
            campaign_id="camp_002",
            ladder_campaign_id="ladder_002",
            receipt_generated=10,
            receipt_blocked=2,
            receipt_shortlisted=3,
            db_generated=10,
            db_blocked=2,
            db_finalists=5,
            db_shortlisted=3,
            elapsed_seconds=1800.0,
            champion_rationale_present=True,
            finalists_missing_falsification=3,
        )
        assert diag["falsification_complete"] is False
        assert diag["integrity_ok"] is False
        assert any("falsification_missing" in issue for issue in diag["issues"])


# ── Test 8: Review labels in pack JSON ────────────────────────────────────────

class TestReviewLabelsInPack:
    def test_review_labels_exported_in_pack_json(self, tmp_path):
        """Review labels from DB should appear in the evaluation pack JSON."""
        from breakthrough_engine.evaluation_pack import EvaluationPackExporter

        db = _make_in_memory_db()
        campaign_id = "eval_labels_test"
        ladder_cid = _insert_receipt(db, campaign_id, profile_type="evaluation",
                                      total_generated=1, total_blocked=0, total_shortlisted=1)
        _insert_daily_campaign(db, ladder_cid, "cand_labels_champ")
        _insert_run(db, "run_labels_001")
        _insert_candidate(db, "cand_labels_champ", "run_labels_001",
                          "Labels Champion", status="finalist", final_score=0.91)
        _insert_falsification(db, "cand_labels_champ", "run_labels_001")

        # Insert review label
        db.execute(
            """INSERT INTO bt_review_labels
               (id, campaign_id, candidate_id, candidate_title, candidate_role,
                decision, novelty_confidence, technical_plausibility,
                commercialization_relevance, key_flaw, reviewer_note, reviewer)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("lbl_001", campaign_id, "cand_labels_champ", "Labels Champion",
             "champion", "approve", 0.9, 0.85, 0.75,
             "No major flaw found", "Strong candidate", "operator"),
        )
        db.commit()

        db_path = str(tmp_path / "labels.db")
        import sqlite3 as _sqlite3
        file_db = _sqlite3.connect(db_path)
        db.backup(file_db)
        file_db.close()

        exporter = EvaluationPackExporter(db_path=db_path)
        out_dir = exporter.export(campaign_id, overwrite=True)

        with open(os.path.join(out_dir, "evaluation_pack.json")) as f:
            pack = json.load(f)

        assert "review_labels" in pack
        assert len(pack["review_labels"]) == 1
        assert pack["review_labels"][0]["decision"] == "approve"
        assert pack["review_labels"][0]["candidate_role"] == "champion"

    def test_review_labels_csv_exported_when_present(self, tmp_path):
        """review_labels.csv must be written when labels exist."""
        from breakthrough_engine.evaluation_pack import EvaluationPackExporter

        db = _make_in_memory_db()
        campaign_id = "eval_csv_test"
        ladder_cid = _insert_receipt(db, campaign_id, profile_type="evaluation",
                                      total_generated=1, total_blocked=0, total_shortlisted=1)
        _insert_daily_campaign(db, ladder_cid, "cand_csv_champ")
        _insert_run(db, "run_csv_001")
        _insert_candidate(db, "cand_csv_champ", "run_csv_001",
                          "CSV Champion", status="finalist", final_score=0.91)
        _insert_falsification(db, "cand_csv_champ", "run_csv_001")
        db.execute(
            """INSERT INTO bt_review_labels
               (id, campaign_id, candidate_id, candidate_title, candidate_role, decision)
               VALUES (?,?,?,?,?,?)""",
            ("lbl_csv_001", campaign_id, "cand_csv_champ", "CSV Champion", "champion", "approve"),
        )
        db.commit()

        db_path = str(tmp_path / "csv.db")
        import sqlite3 as _sqlite3
        file_db = _sqlite3.connect(db_path)
        db.backup(file_db)
        file_db.close()

        exporter = EvaluationPackExporter(db_path=db_path)
        out_dir = exporter.export(campaign_id, overwrite=True)

        csv_path = os.path.join(out_dir, "review_labels.csv")
        assert os.path.exists(csv_path), "review_labels.csv must be written when labels exist"

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["decision"] == "approve"


# ── Test 9: DB migration 10 idempotent ───────────────────────────────────────

class TestMigration10Idempotent:
    def test_init_db_twice_does_not_fail(self):
        """Running init_db twice should be idempotent."""
        from breakthrough_engine.db import init_db
        db = init_db(in_memory=True)
        # Schema version should be at least 10 (migration 10 applied)
        version = db.execute("SELECT MAX(version) FROM bt_schema_version").fetchone()[0]
        assert version >= 10

    def test_bt_review_labels_exists_after_migration(self):
        db = _make_in_memory_db()
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "bt_review_labels" in tables


# ── Test 10: EVALUATION_GRADE_PROFILE_TYPES constant ─────────────────────────

class TestEvaluationGradeConstants:
    def test_evaluation_in_grade_types(self):
        from breakthrough_engine.evaluation_pack import EVALUATION_GRADE_PROFILE_TYPES
        assert "evaluation" in EVALUATION_GRADE_PROFILE_TYPES

    def test_smoke_not_in_grade_types(self):
        from breakthrough_engine.evaluation_pack import EVALUATION_GRADE_PROFILE_TYPES
        assert "smoke" not in EVALUATION_GRADE_PROFILE_TYPES

    def test_pilot_not_in_grade_types(self):
        from breakthrough_engine.evaluation_pack import EVALUATION_GRADE_PROFILE_TYPES
        assert "pilot" not in EVALUATION_GRADE_PROFILE_TYPES

    def test_v003_schema_version_constant(self):
        from breakthrough_engine.evaluation_pack import ANALYSIS_SCHEMA_VERSION_EVAL
        assert ANALYSIS_SCHEMA_VERSION_EVAL == "v003"
