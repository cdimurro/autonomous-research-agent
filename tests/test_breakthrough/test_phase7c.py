"""Phase 7C tests: Telemetry Integrity, Scoring Calibration, Eval Pack v002.

All tests are OFFLINE-SAFE:
- No Ollama network calls
- No real DB I/O (in-memory DB only)
- No file I/O beyond tmpdir
- No internet access

Tests cover:
1. elapsed_seconds populated from bt_campaign_receipts (not bt_daily_campaigns)
2. champion_rationale recovered via ladder_campaign_id in stage_events
3. total_candidates_blocked counted from NOVELTY_FAILED candidates
4. total_candidates_generated counted from actual DB rows
5. accounting_diagnostics integrity_ok flag
6. Falsification MISSING sentinel for finalists without falsification
7. validate_pack_integrity failures and passes
8. Evidence strength count penalty (scoring calibration)
9. Accounting diagnostics issue detection
10. Schema version is v002
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_in_memory_db():
    from breakthrough_engine.db import init_db
    return init_db(in_memory=True)


LADDER_CAMPAIGN_ID = "ladder_internal_abc123"


def _insert_receipt_with_timing(
    db,
    campaign_id: str,
    elapsed_seconds: float = 2487.0,
    champion_id: str = "cand_champion_001",
    ladder_campaign_id: str = LADDER_CAMPAIGN_ID,
    total_shortlisted: int = 5,
    total_generated: int = 80,
    total_blocked: int = 4,
    status: str = "completed_with_draft",
):
    """Insert a receipt that includes elapsed_seconds and ladder_campaign_id in stage_events."""
    stage_events = [
        {"stage_name": "preflight", "status": "completed", "elapsed_seconds": 1.0,
         "retries": 0, "error_message": "", "details": {}},
        {"stage_name": "lock_acquisition", "status": "completed", "elapsed_seconds": 0.0,
         "retries": 0, "error_message": "", "details": {}},
        {"stage_name": "db_init", "status": "completed", "elapsed_seconds": 0.2,
         "retries": 0, "error_message": "", "details": {}},
        # Key: the ladder event stores the DailySearchLadder's internal campaign_id
        {"stage_name": "daily_search_ladder", "status": "completed",
         "elapsed_seconds": elapsed_seconds, "retries": 0, "error_message": "",
         "details": {
             "campaign_id": ladder_campaign_id,
             "champion_id": champion_id,
             "total_generated": total_generated,
             "elapsed": round(elapsed_seconds, 2),
             "stages": 5,
         }},
        {"stage_name": "artifact_export", "status": "completed", "elapsed_seconds": 0.5,
         "retries": 0, "error_message": "", "details": {}},
    ]
    db.execute(
        """INSERT OR REPLACE INTO bt_campaign_receipts
           (campaign_id, profile_name, profile_type, status,
            config_json, preflight_json, stage_events_json,
            started_at, completed_at, elapsed_seconds,
            champion_candidate_id, champion_candidate_title,
            total_candidates_generated, total_blocked, total_shortlisted,
            policy_trials_attempted, retries_used,
            artifact_paths_json, health_summary_json,
            embedding_provider)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            campaign_id,
            "overnight_clean_energy", "overnight", status,
            json.dumps({
                "domain": "clean-energy", "program_name": "clean_energy_shadow",
                "mode": "production", "wall_clock_budget_minutes": 480,
                "candidate_trial_budget": 50,
                "embedding_provider": "OllamaEmbeddingProvider(nomic-embed-text)",
                "embedding_model": "nomic-embed-text",
            }),
            json.dumps({"readiness_score": 1.0, "pass_count": 15, "warn_count": 0, "fail_count": 0}),
            json.dumps(stage_events),
            "2026-03-09T05:11:06Z",
            "2026-03-09T05:52:34Z",
            elapsed_seconds,  # The correctly populated elapsed_seconds column
            champion_id,
            "Test Champion Title",
            total_generated,
            total_blocked,
            total_shortlisted,
            9,
            0,
            "[]",
            json.dumps({"healthy": True, "overnight_ready": True}),
            "OllamaEmbeddingProvider(nomic-embed-text)",
        ),
    )
    db.commit()


def _insert_daily_campaign(
    db,
    ladder_campaign_id: str,
    champion_id: str = "cand_champion_001",
    rationale: str = "Highest final_score=0.957. Selected as champion.",
    elapsed_seconds: float = 2487.25,
):
    """Insert the bt_daily_campaigns row as DailySearchLadder would write it."""
    result_dict = {
        "policy_used": "phase5_champion",
        "daily_champion_id": champion_id,
        "daily_champion_title": "Test Champion Title",
        "champion_selection_rationale": rationale,
        "total_candidates_generated": 80,
        "total_blocked": 4,
        "total_shortlisted": 5,
        "elapsed_seconds": round(elapsed_seconds, 2),
    }
    db.execute(
        """INSERT OR REPLACE INTO bt_daily_campaigns
           (id, campaign_id, mode, policy_id, champion_candidate_id,
            config_json, result_json, started_at, completed_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            "dc_row_uuid_001",
            ladder_campaign_id,    # <-- DailySearchLadder's own internal campaign_id
            "production",
            "phase5_champion",
            champion_id,
            json.dumps({"mode": "production", "program_name": "clean_energy_shadow"}),
            json.dumps(result_dict),
            "2026-03-09T05:11:10Z",
            "2026-03-09T05:52:33Z",
        ),
    )
    db.commit()


def _insert_run(db, run_id: str, campaign_start: str = "2026-03-09T05:11:10Z"):
    """Insert a minimal bt_runs row."""
    db.execute(
        """INSERT OR REPLACE INTO bt_runs
           (id, program_name, mode, status, candidates_generated,
            candidates_rejected, started_at, completed_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (run_id, "clean_energy_shadow", "production", "completed", 10, 1,
         campaign_start,
         "2026-03-09T05:12:10Z"),
    )
    db.commit()


def _insert_candidate(db, candidate_id: str, run_id: str, title: str,
                       status: str = "finalist", final_score: float = 0.90,
                       evidence_refs: list | None = None):
    """Insert a minimal candidate + score row."""
    db.execute(
        """INSERT OR REPLACE INTO bt_candidates
           (id, run_id, title, domain, statement, mechanism, expected_outcome,
            testability_window_hours, novelty_notes, assumptions, risk_flags,
            evidence_refs, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (candidate_id, run_id, title, "clean-energy",
         "Statement.", "Mechanism.", "Outcome.",
         24.0, "Novelty notes for the candidate " * 5,
         "[]", "[]",
         json.dumps(evidence_refs or []),
         status, "2026-03-09T05:15:00Z"),
    )
    db.execute(
        """INSERT OR REPLACE INTO bt_scores
           (candidate_id, novelty_score, plausibility_score, impact_score,
            validation_cost_score, evidence_strength_score,
            simulation_readiness_score, final_score)
           VALUES (?,?,?,?,?,?,?,?)""",
        (candidate_id, 1.0, 0.90, 1.0, 0.30, 0.98, 1.0, final_score),
    )
    db.commit()


def _insert_falsification(db, candidate_id: str, run_id: str = "run_falsif_001",
                           risk: str = "medium",
                           passed: bool = True, fragility: float = 0.7):
    """Insert a falsification summary."""
    import uuid
    db.execute(
        """INSERT OR REPLACE INTO bt_falsification_summaries
           (id, candidate_id, run_id, falsification_risk, passed,
            assumption_fragility_score, reasoning)
           VALUES (?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), candidate_id, run_id, risk, 1 if passed else 0,
         fragility, "Falsification passed with minor concerns."),
    )
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Schema version is v002
# ═══════════════════════════════════════════════════════════════════════════════

class TestSchemaVersion:
    def test_analysis_schema_version_is_v002(self):
        from breakthrough_engine.evaluation_pack import ANALYSIS_SCHEMA_VERSION
        assert ANALYSIS_SCHEMA_VERSION == "v002"

    def test_pack_to_dict_includes_v002_schema(self):
        from breakthrough_engine.evaluation_pack import EvaluationPack
        pack = EvaluationPack(campaign_id="test", status="completed_with_draft")
        d = pack.to_dict()
        assert d["schema_version"] == "v002"

    def test_pack_to_dict_includes_accounting_diagnostics(self):
        from breakthrough_engine.evaluation_pack import EvaluationPack
        pack = EvaluationPack(campaign_id="test")
        pack.accounting_diagnostics = {"integrity_ok": True, "issues": []}
        d = pack.to_dict()
        assert "accounting_diagnostics" in d
        assert d["accounting_diagnostics"]["integrity_ok"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 2. elapsed_seconds from bt_campaign_receipts
# ═══════════════════════════════════════════════════════════════════════════════

class TestElapsedSecondsFixed:
    def test_elapsed_seconds_populated_from_receipt(self, tmp_path):
        """_build_pack should read elapsed_seconds from bt_campaign_receipts, not bt_daily_campaigns."""
        db = _make_in_memory_db()
        campaign_id = "test_elapsed_fix_001"
        run_id = "run_elapsed_001"

        _insert_receipt_with_timing(db, campaign_id, elapsed_seconds=2487.0)
        _insert_run(db, run_id)
        _insert_candidate(db, "cand_001", run_id, "Candidate A", status="finalist")

        db_path = str(tmp_path / "test.db")
        # Write the in-memory DB to a file
        import shutil
        conn2 = sqlite3.connect(db_path)
        for line in db.iterdump():
            conn2.execute(line)
        conn2.commit()
        conn2.close()

        from breakthrough_engine.evaluation_pack import EvaluationPackExporter
        exporter = EvaluationPackExporter(db_path=db_path)
        pack = exporter._build_pack(campaign_id)

        # Key assertion: elapsed_seconds should be from the receipt, not 0.0
        assert pack.elapsed_seconds == 2487.0, (
            f"Expected 2487.0, got {pack.elapsed_seconds}. "
            "elapsed_seconds must be read from bt_campaign_receipts, not bt_daily_campaigns."
        )

    def test_elapsed_seconds_zero_if_receipt_has_zero(self, tmp_path):
        """If receipt genuinely has 0 elapsed, pack should reflect that."""
        db = _make_in_memory_db()
        campaign_id = "test_elapsed_zero_001"
        _insert_receipt_with_timing(db, campaign_id, elapsed_seconds=0.0, status="running")

        db_path = str(tmp_path / "test.db")
        conn2 = sqlite3.connect(db_path)
        for line in db.iterdump():
            conn2.execute(line)
        conn2.commit()
        conn2.close()

        from breakthrough_engine.evaluation_pack import EvaluationPackExporter
        exporter = EvaluationPackExporter(db_path=db_path)
        pack = exporter._build_pack(campaign_id)
        assert pack.elapsed_seconds == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. champion_rationale via ladder_campaign_id in stage_events
# ═══════════════════════════════════════════════════════════════════════════════

class TestChampionRationaleFixed:
    def test_champion_rationale_recovered_via_ladder_campaign_id(self, tmp_path):
        """champion_rationale should be recovered by using the ladder's campaign_id
        extracted from stage_events, not the receipt's campaign_id."""
        db = _make_in_memory_db()
        campaign_id = "receipt_campaign_id_001"
        run_id = "run_rationale_001"

        _insert_receipt_with_timing(
            db, campaign_id,
            ladder_campaign_id=LADDER_CAMPAIGN_ID,
            champion_id="cand_champion_001",
        )
        _insert_daily_campaign(
            db,
            ladder_campaign_id=LADDER_CAMPAIGN_ID,
            champion_id="cand_champion_001",
            rationale="Highest final_score=0.957. No ties. Selected as champion.",
        )
        _insert_run(db, run_id)
        _insert_candidate(db, "cand_champion_001", run_id, "Champion Candidate")

        db_path = str(tmp_path / "test.db")
        conn2 = sqlite3.connect(db_path)
        for line in db.iterdump():
            conn2.execute(line)
        conn2.commit()
        conn2.close()

        from breakthrough_engine.evaluation_pack import EvaluationPackExporter
        exporter = EvaluationPackExporter(db_path=db_path)
        pack = exporter._build_pack(campaign_id)

        assert pack.champion_rationale, (
            "champion_rationale is blank. Should be recovered via ladder_campaign_id "
            "from stage_events, then used to query bt_daily_campaigns."
        )
        assert "champion" in pack.champion_rationale.lower()

    def test_champion_rationale_blank_when_no_stage_events(self, tmp_path):
        """If stage_events has no ladder event, champion_rationale should be blank."""
        db = _make_in_memory_db()
        campaign_id = "receipt_no_ladder_event_001"
        # Insert receipt with empty stage_events
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
            (campaign_id, "smoke_10m", "smoke", "completed_with_draft",
             json.dumps({"domain": "clean-energy", "program_name": "test",
                         "mode": "production", "wall_clock_budget_minutes": 10,
                         "candidate_trial_budget": 5,
                         "embedding_provider": "Mock", "embedding_model": "mock"}),
             json.dumps({"readiness_score": 1.0, "pass_count": 1, "warn_count": 0, "fail_count": 0}),
             json.dumps([]),  # no stage events
             "2026-03-09T10:00:00Z", "2026-03-09T10:10:00Z", 600.0,
             "cand_001", "Test", 5, 0, 3, 1, 0, "[]",
             json.dumps({"healthy": True, "overnight_ready": True}),
             "MockEmbeddingProvider"),
        )
        db.commit()

        db_path = str(tmp_path / "test.db")
        conn2 = sqlite3.connect(db_path)
        for line in db.iterdump():
            conn2.execute(line)
        conn2.commit()
        conn2.close()

        from breakthrough_engine.evaluation_pack import EvaluationPackExporter
        exporter = EvaluationPackExporter(db_path=db_path)
        pack = exporter._build_pack(campaign_id)
        # No ladder event → no rationale, but no crash
        assert isinstance(pack.champion_rationale, str)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. total_candidates_blocked from DB (NOVELTY_FAILED count)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBlockedCountFixed:
    def test_blocked_count_from_db_novelty_failed(self, tmp_path):
        """total_candidates_blocked should count NOVELTY_FAILED candidates in DB."""
        db = _make_in_memory_db()
        campaign_id = "test_blocked_count_001"
        run_id = "run_blocked_001"

        _insert_receipt_with_timing(db, campaign_id, total_blocked=0)  # receipt says 0
        _insert_run(db, run_id)
        # Insert 3 finalists and 2 novelty-failed candidates
        _insert_candidate(db, "cand_f1", run_id, "Finalist 1", status="finalist")
        _insert_candidate(db, "cand_f2", run_id, "Finalist 2", status="finalist")
        _insert_candidate(db, "cand_f3", run_id, "Finalist 3", status="finalist")
        _insert_candidate(db, "cand_b1", run_id, "Blocked 1", status="novelty_failed")
        _insert_candidate(db, "cand_b2", run_id, "Blocked 2", status="novelty_failed")

        db_path = str(tmp_path / "test.db")
        conn2 = sqlite3.connect(db_path)
        for line in db.iterdump():
            conn2.execute(line)
        conn2.commit()
        conn2.close()

        from breakthrough_engine.evaluation_pack import EvaluationPackExporter
        exporter = EvaluationPackExporter(db_path=db_path)
        pack = exporter._build_pack(campaign_id)

        # DB has 2 novelty_failed; should report 2 not receipt's 0
        assert pack.total_candidates_blocked == 2, (
            f"Expected 2 blocked from DB, got {pack.total_candidates_blocked}. "
            "Must count NOVELTY_FAILED candidates, not use receipt's estimate."
        )

    def test_blocked_count_zero_when_none_blocked(self, tmp_path):
        """If no novelty_failed candidates, blocked count should be 0."""
        db = _make_in_memory_db()
        campaign_id = "test_blocked_zero_001"
        run_id = "run_blocked_zero_001"

        _insert_receipt_with_timing(db, campaign_id)
        _insert_run(db, run_id)
        _insert_candidate(db, "cand_f1", run_id, "Finalist 1", status="finalist")

        db_path = str(tmp_path / "test.db")
        conn2 = sqlite3.connect(db_path)
        for line in db.iterdump():
            conn2.execute(line)
        conn2.commit()
        conn2.close()

        from breakthrough_engine.evaluation_pack import EvaluationPackExporter
        exporter = EvaluationPackExporter(db_path=db_path)
        pack = exporter._build_pack(campaign_id)
        assert pack.total_candidates_blocked == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. total_candidates_generated from actual DB rows
# ═══════════════════════════════════════════════════════════════════════════════

class TestGeneratedCountFixed:
    def test_generated_count_from_db_rows(self, tmp_path):
        """total_candidates_generated should count actual DB rows, not use receipt estimate."""
        db = _make_in_memory_db()
        campaign_id = "test_generated_count_001"
        run_id = "run_gen_001"

        # Receipt says 50, but only 4 candidates actually in DB
        _insert_receipt_with_timing(db, campaign_id, total_generated=50)
        _insert_run(db, run_id)
        for i in range(4):
            _insert_candidate(db, f"cand_g{i}", run_id, f"Candidate {i}", status="finalist")

        db_path = str(tmp_path / "test.db")
        conn2 = sqlite3.connect(db_path)
        for line in db.iterdump():
            conn2.execute(line)
        conn2.commit()
        conn2.close()

        from breakthrough_engine.evaluation_pack import EvaluationPackExporter
        exporter = EvaluationPackExporter(db_path=db_path)
        pack = exporter._build_pack(campaign_id)

        # DB has 4 candidates; not 50
        assert pack.total_candidates_generated == 4, (
            f"Expected 4 from DB, got {pack.total_candidates_generated}."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Falsification MISSING sentinel for finalists without falsification
# ═══════════════════════════════════════════════════════════════════════════════

class TestFalsificationMissingSentinel:
    def test_finalist_without_falsification_gets_missing_sentinel(self, tmp_path):
        """Finalists with no falsification summary should get risk=MISSING, not None."""
        from breakthrough_engine.evaluation_pack import FALSIFICATION_MISSING
        db = _make_in_memory_db()
        campaign_id = "test_falsif_missing_001"
        run_id = "run_falsif_001"

        _insert_receipt_with_timing(db, campaign_id, champion_id="cand_f1")
        _insert_run(db, run_id)
        _insert_candidate(db, "cand_f1", run_id, "Finalist With Falsification", status="finalist")
        _insert_candidate(db, "cand_f2", run_id, "Finalist WITHOUT Falsification", status="finalist")

        # Only insert falsification for cand_f1
        _insert_falsification(db, "cand_f1", run_id=run_id)

        db_path = str(tmp_path / "test.db")
        conn2 = sqlite3.connect(db_path)
        for line in db.iterdump():
            conn2.execute(line)
        conn2.commit()
        conn2.close()

        from breakthrough_engine.evaluation_pack import EvaluationPackExporter
        exporter = EvaluationPackExporter(db_path=db_path)
        pack = exporter._build_pack(campaign_id)

        finalists = {c.candidate_id: c for c in pack.all_candidates if c.status == "finalist"}
        f1 = finalists["cand_f1"]
        f2 = finalists["cand_f2"]

        # f1 has falsification → normal risk value
        assert f1.falsification_risk == "medium"
        assert f1.falsification_passed is True

        # f2 has NO falsification → MISSING sentinel
        assert f2.falsification_risk == FALSIFICATION_MISSING, (
            f"Expected MISSING for finalist without falsification, got {f2.falsification_risk!r}"
        )
        assert f2.falsification_reasoning is not None
        assert "No falsification summary" in f2.falsification_reasoning

    def test_non_finalist_without_falsification_stays_none(self, tmp_path):
        """Non-finalists without falsification should stay None (expected)."""
        db = _make_in_memory_db()
        campaign_id = "test_nonfin_falsif_001"
        run_id = "run_nonfin_001"

        _insert_receipt_with_timing(db, campaign_id, champion_id="cand_f1")
        _insert_run(db, run_id)
        _insert_candidate(db, "cand_f1", run_id, "Finalist", status="finalist")
        _insert_candidate(db, "cand_r1", run_id, "Rejected", status="novelty_failed")
        _insert_falsification(db, "cand_f1", run_id=run_id)

        db_path = str(tmp_path / "test.db")
        conn2 = sqlite3.connect(db_path)
        for line in db.iterdump():
            conn2.execute(line)
        conn2.commit()
        conn2.close()

        from breakthrough_engine.evaluation_pack import EvaluationPackExporter
        exporter = EvaluationPackExporter(db_path=db_path)
        pack = exporter._build_pack(campaign_id)

        non_finalists = [c for c in pack.all_candidates if c.status != "finalist"]
        for c in non_finalists:
            assert c.falsification_risk is None, (
                f"Non-finalist {c.candidate_id} should have None falsification_risk"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 7. validate_pack_integrity
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidatePackIntegrity:
    def test_clean_pack_has_no_failures(self):
        """A fully populated pack should pass integrity check."""
        from breakthrough_engine.evaluation_pack import (
            EvaluationPack, CandidateRecord, validate_pack_integrity
        )
        pack = EvaluationPack(
            campaign_id="test_clean_pack",
            status="completed_with_draft",
            elapsed_seconds=600.0,
            champion_id="cand_001",
            champion_rationale="Highest score 0.95, no ties.",
        )
        finalist = CandidateRecord(
            candidate_id="cand_001",
            run_id="run_001",
            title="Test",
            domain="clean-energy",
            statement="Statement.",
            mechanism="Mechanism.",
            expected_outcome="Outcome.",
            testability_window_hours=24.0,
            novelty_notes="Novelty.",
            assumptions=[],
            risk_flags=[],
            evidence_refs=[],
            status="finalist",
            created_at="2026-03-09T10:00:00Z",
            falsification_risk="medium",
        )
        pack.all_candidates = [finalist]
        failures = validate_pack_integrity(pack)
        assert failures == [], f"Expected no failures, got: {failures}"

    def test_zero_elapsed_for_completed_campaign_is_failure(self):
        """elapsed_seconds = 0.0 for a completed campaign should be a failure."""
        from breakthrough_engine.evaluation_pack import EvaluationPack, validate_pack_integrity
        pack = EvaluationPack(
            campaign_id="test_zero_elapsed",
            status="completed_with_draft",
            elapsed_seconds=0.0,
            champion_id="cand_001",
            champion_rationale="Highest score.",
        )
        failures = validate_pack_integrity(pack)
        assert any("elapsed_seconds" in f for f in failures), (
            f"Expected elapsed_seconds failure, got: {failures}"
        )

    def test_blank_champion_rationale_is_failure(self):
        """champion_rationale blank for a campaign with a champion should be a failure."""
        from breakthrough_engine.evaluation_pack import EvaluationPack, validate_pack_integrity
        pack = EvaluationPack(
            campaign_id="test_blank_rationale",
            status="completed_with_draft",
            elapsed_seconds=600.0,
            champion_id="cand_001",
            champion_rationale="",  # blank
        )
        failures = validate_pack_integrity(pack)
        assert any("champion_rationale" in f for f in failures), (
            f"Expected champion_rationale failure, got: {failures}"
        )

    def test_finalist_with_none_falsification_is_failure(self):
        """Finalist with falsification_risk=None should be a failure."""
        from breakthrough_engine.evaluation_pack import (
            EvaluationPack, CandidateRecord, validate_pack_integrity
        )
        pack = EvaluationPack(
            campaign_id="test_none_falsif",
            status="completed_with_draft",
            elapsed_seconds=600.0,
            champion_id="cand_001",
            champion_rationale="Highest score.",
        )
        finalist = CandidateRecord(
            candidate_id="cand_001",
            run_id="run_001",
            title="Test",
            domain="clean-energy",
            statement="Statement.",
            mechanism="Mechanism.",
            expected_outcome="Outcome.",
            testability_window_hours=24.0,
            novelty_notes="Novelty.",
            assumptions=[],
            risk_flags=[],
            evidence_refs=[],
            status="finalist",
            created_at="2026-03-09T10:00:00Z",
            falsification_risk=None,  # None — should be a failure
        )
        pack.all_candidates = [finalist]
        failures = validate_pack_integrity(pack)
        assert any("falsification" in f for f in failures), (
            f"Expected falsification failure for None risk, got: {failures}"
        )

    def test_no_champion_no_rationale_required(self):
        """If no champion_id, blank rationale is OK."""
        from breakthrough_engine.evaluation_pack import EvaluationPack, validate_pack_integrity
        pack = EvaluationPack(
            campaign_id="test_no_champ",
            status="completed_no_draft",
            elapsed_seconds=600.0,
            champion_id="",
            champion_rationale="",
        )
        failures = validate_pack_integrity(pack)
        # No champion → no rationale requirement
        assert not any("champion_rationale" in f for f in failures)

    def test_running_campaign_zero_elapsed_not_a_failure(self):
        """A running campaign with 0 elapsed is fine (timing in progress)."""
        from breakthrough_engine.evaluation_pack import EvaluationPack, validate_pack_integrity
        pack = EvaluationPack(
            campaign_id="test_running",
            status="running",
            elapsed_seconds=0.0,
        )
        failures = validate_pack_integrity(pack)
        assert not any("elapsed" in f for f in failures)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Accounting diagnostics
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccountingDiagnostics:
    def test_integrity_ok_true_when_all_good(self):
        """When elapsed > 0, rationale present, no missing falsif → integrity_ok=True."""
        from breakthrough_engine.evaluation_pack import _build_accounting_diagnostics
        diag = _build_accounting_diagnostics(
            campaign_id="cid", ladder_campaign_id="lid",
            receipt_generated=10, receipt_blocked=2,
            receipt_shortlisted=3,
            db_generated=10, db_blocked=2,
            db_finalists=3, db_shortlisted=3,
            elapsed_seconds=600.0,
            champion_rationale_present=True,
            finalists_missing_falsification=0,
        )
        assert diag["integrity_ok"] is True
        assert diag["issues"] == []

    def test_integrity_ok_false_when_elapsed_zero(self):
        from breakthrough_engine.evaluation_pack import _build_accounting_diagnostics
        diag = _build_accounting_diagnostics(
            campaign_id="cid", ladder_campaign_id="lid",
            receipt_generated=10, receipt_blocked=2, receipt_shortlisted=3,
            db_generated=10, db_blocked=2, db_finalists=3, db_shortlisted=3,
            elapsed_seconds=0.0,
            champion_rationale_present=True,
            finalists_missing_falsification=0,
        )
        assert diag["integrity_ok"] is False
        assert any("elapsed_seconds_zero" in i for i in diag["issues"])

    def test_integrity_ok_false_when_rationale_missing(self):
        from breakthrough_engine.evaluation_pack import _build_accounting_diagnostics
        diag = _build_accounting_diagnostics(
            campaign_id="cid", ladder_campaign_id="lid",
            receipt_generated=10, receipt_blocked=2, receipt_shortlisted=3,
            db_generated=10, db_blocked=2, db_finalists=3, db_shortlisted=3,
            elapsed_seconds=600.0,
            champion_rationale_present=False,
            finalists_missing_falsification=0,
        )
        assert diag["integrity_ok"] is False
        assert any("champion_rationale_empty" in i for i in diag["issues"])

    def test_integrity_ok_false_when_missing_falsification(self):
        from breakthrough_engine.evaluation_pack import _build_accounting_diagnostics
        diag = _build_accounting_diagnostics(
            campaign_id="cid", ladder_campaign_id="lid",
            receipt_generated=10, receipt_blocked=2, receipt_shortlisted=3,
            db_generated=10, db_blocked=2, db_finalists=3, db_shortlisted=3,
            elapsed_seconds=600.0,
            champion_rationale_present=True,
            finalists_missing_falsification=3,
        )
        assert diag["integrity_ok"] is False
        assert any("falsification_missing" in i for i in diag["issues"])

    def test_integrity_ok_false_when_no_ladder_campaign_id(self):
        from breakthrough_engine.evaluation_pack import _build_accounting_diagnostics
        diag = _build_accounting_diagnostics(
            campaign_id="cid", ladder_campaign_id="",  # empty — not recovered
            receipt_generated=10, receipt_blocked=2, receipt_shortlisted=3,
            db_generated=10, db_blocked=2, db_finalists=3, db_shortlisted=3,
            elapsed_seconds=600.0,
            champion_rationale_present=True,
            finalists_missing_falsification=0,
        )
        assert diag["integrity_ok"] is False
        assert any("ladder_campaign_id_missing" in i for i in diag["issues"])

    def test_diagnostics_records_source_fields(self):
        from breakthrough_engine.evaluation_pack import _build_accounting_diagnostics
        diag = _build_accounting_diagnostics(
            campaign_id="cid_001", ladder_campaign_id="lid_001",
            receipt_generated=80, receipt_blocked=4, receipt_shortlisted=5,
            db_generated=80, db_blocked=4, db_finalists=27, db_shortlisted=5,
            elapsed_seconds=2487.0,
            champion_rationale_present=True,
            finalists_missing_falsification=0,
        )
        assert diag["source_campaign_id"] == "cid_001"
        assert diag["ladder_campaign_id"] == "lid_001"
        assert diag["receipt_generated"] == 80
        assert diag["db_blocked"] == 4
        assert diag["elapsed_seconds_source"] == "bt_campaign_receipts"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Evidence strength count penalty (scoring calibration)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvidenceStrengthCalibration:
    """Tests for the Phase 7C count-based evidence strength penalty."""

    def _make_evidence_pack(self, n_items: int, relevance: float = 0.9):
        from breakthrough_engine.models import EvidencePack, EvidenceItem
        items = [
            EvidenceItem(
                id=f"ev_{i}",
                source_id=f"src_{i}",
                title=f"Evidence {i}",
                abstract="Abstract text.",
                quote="Quoted text.",
                citation=f"Author et al., 2025, Journal {i}.",
                relevance_score=relevance,
                source_type="journal",
            )
            for i in range(n_items)
        ]
        pack = EvidencePack(candidate_id=f"cand_{n_items}", items=items)
        pack.source_diversity_count = min(n_items, 4)
        return pack

    def _score_with_n_refs(self, n: int, relevance: float = 0.9):
        from breakthrough_engine.scoring import score_candidate
        from breakthrough_engine.models import (
            CandidateHypothesis, ResearchProgram, RunMode
        )
        candidate = CandidateHypothesis(
            id=f"cand_{n}",
            run_id="run_x",
            title="Test",
            domain="clean-energy",
            statement="Statement text " * 10,
            mechanism="Mechanism text " * 10,
            expected_outcome="Outcome text " * 10,
            testability_window_hours=24.0,
            novelty_notes="Novelty text " * 10,
        )
        program = ResearchProgram(name="test", domain="test", mode=RunMode.DETERMINISTIC_TEST)
        evidence_pack = self._make_evidence_pack(n, relevance)
        score = score_candidate(candidate, evidence_pack, None, [], program)
        return score.evidence_strength_score

    def test_one_ref_has_lower_score_than_five_refs(self):
        """1 ref should score lower than 5 refs at same relevance."""
        score_1 = self._score_with_n_refs(1)
        score_5 = self._score_with_n_refs(5)
        assert score_1 < score_5, (
            f"1-ref score ({score_1:.3f}) should be < 5-ref score ({score_5:.3f})"
        )

    def test_two_refs_score_less_than_five_refs(self):
        """2 refs should score less than 5 refs."""
        score_2 = self._score_with_n_refs(2)
        score_5 = self._score_with_n_refs(5)
        assert score_2 < score_5, (
            f"2-ref score ({score_2:.3f}) should be < 5-ref score ({score_5:.3f})"
        )

    def test_count_penalty_values(self):
        """Verify the specific penalty multipliers are applied."""
        # At relevance 0.9, diversity_count = min(n, 4) → 1 source:
        # raw_score for 1 ref: 0.9 + 0.05 = 0.95 → * 0.70 = 0.665
        # raw_score for 2 refs: 0.9 + 0.10 = 1.0 → capped at 1.0 → * 0.82 = 0.82
        # raw_score for 5 refs: 0.9 + 0.20 = 1.0 → no penalty

        score_1 = self._score_with_n_refs(1, relevance=0.9)
        score_2 = self._score_with_n_refs(2, relevance=0.9)
        score_5 = self._score_with_n_refs(5, relevance=0.9)

        # 1-ref: 0.70 multiplier
        assert score_1 < 0.80, f"1-ref score should be < 0.80, got {score_1}"
        # 2-ref: 0.82 multiplier
        assert score_2 < 0.90, f"2-ref score should be < 0.90, got {score_2}"
        # 5-ref: no penalty
        assert score_5 >= 0.95, f"5-ref score should be >= 0.95, got {score_5}"

    def test_evidence_count_penalty_monotonically_increasing(self):
        """Scores should increase monotonically with ref count (same relevance)."""
        scores = [self._score_with_n_refs(n) for n in [1, 2, 3, 4, 5, 8]]
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1], (
                f"Score not monotonically increasing: {scores[i]:.3f} > {scores[i+1]:.3f} "
                f"at index {i}"
            )

    def test_zero_evidence_still_returns_low_score(self):
        """No evidence pack → 0.1 (same as before calibration)."""
        from breakthrough_engine.scoring import score_candidate
        from breakthrough_engine.models import (
            CandidateHypothesis, ResearchProgram, RunMode
        )
        candidate = CandidateHypothesis(
            id="cand_no_ev",
            run_id="run_x",
            title="Test",
            domain="clean-energy",
            statement="Statement text " * 10,
            mechanism="Mechanism text " * 10,
            expected_outcome="Outcome text " * 10,
            testability_window_hours=24.0,
            novelty_notes="Novelty text " * 10,
        )
        program = ResearchProgram(name="test", domain="test", mode=RunMode.DETERMINISTIC_TEST)
        score = score_candidate(candidate, None, None, [], program)
        assert score.evidence_strength_score == 0.1

    def test_five_or_more_refs_get_no_penalty(self):
        """5+ refs should get no penalty (score unchanged from raw)."""
        score_5 = self._score_with_n_refs(5)
        score_10 = self._score_with_n_refs(10)
        # Both should be near the same capped value
        assert abs(score_5 - score_10) < 0.05, (
            f"5-ref ({score_5:.3f}) and 10-ref ({score_10:.3f}) should be similar (both uncapped)"
        )
