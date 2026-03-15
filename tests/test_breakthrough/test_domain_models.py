"""Tests for domain optimization loop contracts (CC-BE-2402)."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from breakthrough_engine.domain_models import (
    CandidateSpec,
    CandidateStatus,
    DomainSpec,
    EvaluationResult,
    ExperimentMemoryEntry,
    ExperimentRunResult,
    ExperimentTemplate,
    IdeaMemoryEntry,
    MetricSpec,
    PromotionDecision,
    PromotionRecord,
)
from breakthrough_engine.db import Repository, init_db


# ---------------------------------------------------------------------------
# Model construction tests
# ---------------------------------------------------------------------------

class TestMetricSpec:
    def test_basic(self):
        m = MetricSpec(name="efficiency", unit="%", higher_is_better=True, is_primary=True)
        assert m.name == "efficiency"
        assert m.unit == "%"
        assert m.higher_is_better is True
        assert m.is_primary is True

    def test_bounds(self):
        m = MetricSpec(name="fill_factor", unit="", lower_bound=0.0, upper_bound=1.0)
        assert m.lower_bound == 0.0
        assert m.upper_bound == 1.0


class TestDomainSpec:
    def test_pv_domain(self):
        d = DomainSpec(
            name="pv_iv",
            display_name="PV I-V Characterization",
            description="Photovoltaic current-voltage characterization",
            metrics=[
                MetricSpec(name="Voc", unit="V", is_primary=True),
                MetricSpec(name="Isc", unit="A"),
                MetricSpec(name="efficiency", unit="%", lower_bound=0, upper_bound=100),
            ],
            banned_claims=["perpetual motion", "over-unity"],
        )
        assert d.name == "pv_iv"
        assert len(d.metrics) == 3
        assert d.metrics[0].is_primary is True
        assert len(d.banned_claims) == 2


class TestExperimentTemplate:
    def test_stc_template(self):
        t = ExperimentTemplate(
            domain_name="pv_iv",
            name="stc_baseline",
            description="Standard Test Conditions: 1000 W/m2, 25C, AM1.5",
            parameters={"irradiance": 1000, "temperature": 25, "spectrum": "AM1.5"},
        )
        assert t.name == "stc_baseline"
        assert t.parameters["irradiance"] == 1000


class TestCandidateSpec:
    def test_basic(self):
        c = CandidateSpec(
            domain_name="pv_iv",
            title="Increased doping concentration",
            parameters={"n_doping": 1e17, "p_doping": 1e16},
            rationale="Higher doping may improve Voc",
        )
        assert c.status == CandidateStatus.PROPOSED
        assert c.domain_name == "pv_iv"
        assert len(c.id) == 16

    def test_derived_candidate(self):
        parent = CandidateSpec(domain_name="pv_iv", title="Base")
        child = CandidateSpec(
            domain_name="pv_iv",
            title="Variation",
            parent_id=parent.id,
            source="perturbation",
        )
        assert child.parent_id == parent.id


class TestExperimentRunResult:
    def test_basic(self):
        r = ExperimentRunResult(
            candidate_id="cand1",
            template_id="tmpl1",
            domain_name="pv_iv",
            metrics={"Voc": 0.65, "Isc": 9.5, "Pmax": 4.2, "fill_factor": 0.78},
            duration_seconds=1.2,
        )
        assert r.metrics["Voc"] == 0.65
        assert r.success is True


class TestEvaluationResult:
    def test_pass(self):
        e = EvaluationResult(
            candidate_id="cand1",
            domain_name="pv_iv",
            score_components={"pmax_improvement": 0.8, "ff_improvement": 0.6},
            final_score=0.72,
        )
        assert e.hard_fail is False
        assert e.final_score == 0.72

    def test_hard_fail(self):
        e = EvaluationResult(
            candidate_id="cand1",
            domain_name="pv_iv",
            final_score=0.0,
            hard_fail=True,
            hard_fail_reasons=["Voc below physical minimum"],
        )
        assert e.hard_fail is True


class TestPromotionRecord:
    def test_promoted(self):
        p = PromotionRecord(
            candidate_id="cand1",
            domain_name="pv_iv",
            decision=PromotionDecision.PROMOTED,
            reason="Improved Pmax by 5% with stable FF",
            baseline_score=0.70,
            candidate_score=0.75,
        )
        assert p.decision == PromotionDecision.PROMOTED

    def test_rejected(self):
        p = PromotionRecord(
            candidate_id="cand2",
            domain_name="pv_iv",
            decision=PromotionDecision.REJECTED,
            reason="Fill factor collapsed under temperature sweep",
        )
        assert p.decision == PromotionDecision.REJECTED


class TestIdeaMemoryEntry:
    def test_basic(self):
        m = IdeaMemoryEntry(
            domain_name="pv_iv",
            candidate_id="cand1",
            candidate_title="High-doping variant",
            candidate_family="doping_variations",
            rationale="Literature suggests higher doping improves Voc",
            outcome="rejected",
            lesson="Doping above 1e18 degrades fill factor due to recombination",
            tags=["doping", "Voc", "fill_factor"],
        )
        assert m.candidate_family == "doping_variations"
        assert len(m.tags) == 3


class TestExperimentMemoryEntry:
    def test_basic(self):
        m = ExperimentMemoryEntry(
            domain_name="pv_iv",
            candidate_id="cand1",
            template_name="temperature_sweep",
            informative_metrics=["Voc", "fill_factor"],
            weakness_exposed="Fill factor drops sharply above 60C",
            runtime_seconds=2.5,
            reproducibility_score=0.95,
        )
        assert m.template_name == "temperature_sweep"
        assert m.reproducibility_score == 0.95


# ---------------------------------------------------------------------------
# Database persistence tests
# ---------------------------------------------------------------------------

@pytest.fixture
def db_repo():
    db = init_db(in_memory=True)
    return Repository(db)


class TestDomainCandidatePersistence:
    def test_save_and_retrieve(self, db_repo):
        c = CandidateSpec(
            domain_name="pv_iv",
            title="Test candidate",
            parameters={"n_doping": 1e17},
            rationale="Test",
        )
        db_repo.save_domain_candidate(c)
        row = db_repo.get_domain_candidate(c.id)
        assert row is not None
        assert row["title"] == "Test candidate"
        assert row["domain_name"] == "pv_iv"
        assert json.loads(row["parameters"])["n_doping"] == 1e17

    def test_list_by_domain(self, db_repo):
        for i in range(3):
            c = CandidateSpec(domain_name="pv_iv", title=f"Candidate {i}")
            db_repo.save_domain_candidate(c)
        c_other = CandidateSpec(domain_name="battery", title="Battery candidate")
        db_repo.save_domain_candidate(c_other)

        pv_candidates = db_repo.list_domain_candidates("pv_iv")
        assert len(pv_candidates) == 3
        battery_candidates = db_repo.list_domain_candidates("battery")
        assert len(battery_candidates) == 1

    def test_update_status(self, db_repo):
        c = CandidateSpec(domain_name="pv_iv", title="Test")
        db_repo.save_domain_candidate(c)
        db_repo.update_domain_candidate_status(c.id, "promoted")
        row = db_repo.get_domain_candidate(c.id)
        assert row["status"] == "promoted"


class TestExperimentResultPersistence:
    def test_save_and_list(self, db_repo):
        r = ExperimentRunResult(
            candidate_id="cand1",
            template_id="stc",
            domain_name="pv_iv",
            metrics={"Voc": 0.65, "Isc": 9.5},
            duration_seconds=1.0,
        )
        db_repo.save_experiment_result(r)
        results = db_repo.list_experiment_results("cand1")
        assert len(results) == 1
        assert json.loads(results[0]["metrics"])["Voc"] == 0.65


class TestEvaluationResultPersistence:
    def test_save(self, db_repo):
        e = EvaluationResult(
            candidate_id="cand1",
            domain_name="pv_iv",
            score_components={"pmax": 0.8},
            final_score=0.8,
        )
        db_repo.save_evaluation_result(e)
        # Verify by raw query
        row = db_repo.db.execute(
            "SELECT * FROM bt_evaluation_results WHERE id=?", (e.id,)
        ).fetchone()
        assert row is not None
        assert row["final_score"] == 0.8


class TestPromotionRecordPersistence:
    def test_save_and_list(self, db_repo):
        p = PromotionRecord(
            candidate_id="cand1",
            domain_name="pv_iv",
            decision=PromotionDecision.PROMOTED,
            reason="Better than baseline",
            baseline_score=0.7,
            candidate_score=0.75,
        )
        db_repo.save_promotion_record(p)
        records = db_repo.list_promotion_records("pv_iv")
        assert len(records) == 1
        assert records[0]["decision"] == "promoted"


class TestIdeaMemoryPersistence:
    def test_save_and_list(self, db_repo):
        m = IdeaMemoryEntry(
            domain_name="pv_iv",
            candidate_id="cand1",
            candidate_title="Test idea",
            candidate_family="test_family",
            lesson="Learned something",
            tags=["tag1"],
        )
        db_repo.save_idea_memory(m)
        entries = db_repo.list_idea_memory("pv_iv")
        assert len(entries) == 1
        assert entries[0]["candidate_family"] == "test_family"
        assert json.loads(entries[0]["tags"]) == ["tag1"]


class TestExperimentMemoryPersistence:
    def test_save_and_list(self, db_repo):
        m = ExperimentMemoryEntry(
            domain_name="pv_iv",
            candidate_id="cand1",
            template_name="stc_baseline",
            informative_metrics=["Voc", "Pmax"],
            weakness_exposed="Low FF at high temp",
            runtime_seconds=2.0,
        )
        db_repo.save_experiment_memory(m)
        entries = db_repo.list_experiment_memory("pv_iv")
        assert len(entries) == 1
        assert entries[0]["template_name"] == "stc_baseline"


# ---------------------------------------------------------------------------
# Lock fix tests
# ---------------------------------------------------------------------------

class TestStaleLockFix:
    def test_stale_lock_auto_cleared(self, tmp_path):
        """Preflight should auto-clear locks from dead PIDs."""
        lock_path = tmp_path / "campaign.lock"
        lock_info = {"campaign_id": "test", "pid": 99999999, "acquired_at": "2026-01-01T00:00:00Z"}
        lock_path.write_text(json.dumps(lock_info))

        os.environ["SCIRES_RUNTIME_ROOT"] = str(tmp_path)
        try:
            from breakthrough_engine.preflight import PreflightEngine
            checker = PreflightEngine.__new__(PreflightEngine)
            result = checker._check_campaign_lock()
            assert result.status == "PASS"
            assert "auto-cleared" in result.detail
            assert not lock_path.exists()
        finally:
            os.environ.pop("SCIRES_RUNTIME_ROOT", None)

    def test_corrupt_lock_auto_cleared(self, tmp_path):
        """Corrupt lock files should be auto-cleared."""
        lock_path = tmp_path / "campaign.lock"
        lock_path.write_text("not valid json {{{")

        os.environ["SCIRES_RUNTIME_ROOT"] = str(tmp_path)
        try:
            from breakthrough_engine.preflight import PreflightEngine
            checker = PreflightEngine.__new__(PreflightEngine)
            result = checker._check_campaign_lock()
            assert result.status == "PASS"
            assert "auto-cleared" in result.detail
            assert not lock_path.exists()
        finally:
            os.environ.pop("SCIRES_RUNTIME_ROOT", None)

    def test_no_lock_passes(self, tmp_path):
        """No lock file should pass."""
        os.environ["SCIRES_RUNTIME_ROOT"] = str(tmp_path)
        try:
            from breakthrough_engine.preflight import PreflightEngine
            checker = PreflightEngine.__new__(PreflightEngine)
            result = checker._check_campaign_lock()
            assert result.status == "PASS"
        finally:
            os.environ.pop("SCIRES_RUNTIME_ROOT", None)

    def test_live_lock_fails(self, tmp_path):
        """Lock from current (live) PID should fail."""
        lock_path = tmp_path / "campaign.lock"
        lock_info = {"campaign_id": "test", "pid": os.getpid(), "acquired_at": "2026-01-01T00:00:00Z"}
        lock_path.write_text(json.dumps(lock_info))

        os.environ["SCIRES_RUNTIME_ROOT"] = str(tmp_path)
        try:
            from breakthrough_engine.preflight import PreflightEngine
            checker = PreflightEngine.__new__(PreflightEngine)
            result = checker._check_campaign_lock()
            assert result.status == "FAIL"
            assert lock_path.exists()
        finally:
            os.environ.pop("SCIRES_RUNTIME_ROOT", None)
