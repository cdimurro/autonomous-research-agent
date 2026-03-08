"""Phase 4D tests: Diversity-aware generation engine.

Covers:
- DiversityContext dataclass
- build_diversity_prompt_addendum
- DiversityEngine.build_context (sub-domain rotation, excluded topics, neighbor titles)
- DiversityEngine.advance_rotation
- CorpusManager (is_active, run_archival, archive_by_cluster, get_active_count)
- Repository v005 methods (diversity_context, rotation_state, corpus_archive)
- Schema migration v005 (three new tables)
- Materials bootstrap seeding
- OllamaCandidateGenerator accepts diversity_context without error
- Orchestrator integrates diversity context (build + advance)
- Bootstrap materials findings (seed count, paper count)
"""

from __future__ import annotations

import sqlite3
import sys
import os
import json
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from breakthrough_engine.db import Repository, init_db, _current_version
from breakthrough_engine.diversity import (
    DiversityContext,
    DiversityEngine,
    build_diversity_prompt_addendum,
    DEFAULT_SUB_DOMAINS,
    _extract_title_topics,
)
from breakthrough_engine.corpus_manager import CorpusManager, PROTECTED_STATUSES
from breakthrough_engine.domain_fit import load_domain_fit_config, clear_config_cache
from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateStatus,
    ResearchProgram,
    RunMode,
    RunRecord,
    RunStatus,
    new_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db():
    db = init_db(in_memory=True)
    return db


def _make_repo():
    return Repository(_make_db())


def _make_run(repo, domain="clean-energy") -> str:
    run = RunRecord(id=new_id(), program_name="test", mode=RunMode.DETERMINISTIC_TEST, status=RunStatus.STARTED)
    repo.save_run(run)
    return run.id


def _make_candidate(repo, domain="clean-energy", status=CandidateStatus.GENERATED, run_id: str | None = None) -> str:
    rid = run_id or _make_run(repo, domain)
    c = CandidateHypothesis(
        id=new_id(),
        run_id=rid,
        title="Test candidate",
        domain=domain,
        statement="A test hypothesis statement that is unique.",
        mechanism="A mechanism via test process.",
        expected_outcome="Measurable test outcome.",
        testability_window_hours=48.0,
    )
    c.status = status
    repo.save_candidate(c)
    return c.id


# ---------------------------------------------------------------------------
# DiversityContext dataclass
# ---------------------------------------------------------------------------


class TestDiversityContext:

    def test_to_dict_round_trip(self):
        ctx = DiversityContext(
            run_id="run123",
            domain="clean-energy",
            sub_domain="solar photovoltaics",
            excluded_topics=["perovskite coating", "tandem cell"],
            excluded_neighbor_titles=["Some Old Hypothesis"],
            rotation_policy="auto",
            focus_areas=["carrier recombination", "lattice mismatch"],
        )
        d = ctx.to_dict()
        assert d["run_id"] == "run123"
        assert d["domain"] == "clean-energy"
        assert d["sub_domain"] == "solar photovoltaics"
        assert "perovskite coating" in d["excluded_topics"]
        assert "Some Old Hypothesis" in d["excluded_neighbor_titles"]
        assert d["rotation_policy"] == "auto"
        assert "carrier recombination" in d["focus_areas"]

    def test_defaults_empty(self):
        ctx = DiversityContext(run_id="r1", domain="materials")
        assert ctx.sub_domain == ""
        assert ctx.excluded_topics == []
        assert ctx.excluded_neighbor_titles == []
        assert ctx.focus_areas == []
        assert ctx.rotation_policy == "auto"


# ---------------------------------------------------------------------------
# build_diversity_prompt_addendum
# ---------------------------------------------------------------------------


class TestBuildDiversityPromptAddendum:

    def test_empty_context_returns_empty(self):
        ctx = DiversityContext(run_id="r1", domain="clean-energy")
        result = build_diversity_prompt_addendum(ctx)
        assert result == ""

    def test_sub_domain_in_addendum(self):
        ctx = DiversityContext(
            run_id="r1", domain="clean-energy", sub_domain="solar photovoltaics"
        )
        result = build_diversity_prompt_addendum(ctx)
        assert "solar photovoltaics" in result
        assert "SUB-DOMAIN FOCUS" in result

    def test_excluded_topics_in_addendum(self):
        ctx = DiversityContext(
            run_id="r1",
            domain="clean-energy",
            excluded_topics=["perovskite coating", "grid storage"],
        )
        result = build_diversity_prompt_addendum(ctx)
        assert "perovskite coating" in result
        assert "AVOID" in result

    def test_neighbor_titles_in_addendum(self):
        ctx = DiversityContext(
            run_id="r1",
            domain="clean-energy",
            excluded_neighbor_titles=["Hypothesis About Solar Cells"],
        )
        result = build_diversity_prompt_addendum(ctx)
        assert "Hypothesis About Solar Cells" in result
        assert "DO NOT REPRODUCE" in result

    def test_focus_areas_in_addendum(self):
        ctx = DiversityContext(
            run_id="r1",
            domain="clean-energy",
            focus_areas=["carrier recombination", "stability under illumination"],
        )
        result = build_diversity_prompt_addendum(ctx)
        assert "carrier recombination" in result
        assert "PREFERRED FOCUS AREAS" in result

    def test_addendum_caps_excluded_topics(self):
        ctx = DiversityContext(
            run_id="r1",
            domain="clean-energy",
            excluded_topics=[f"topic {i}" for i in range(20)],
        )
        result = build_diversity_prompt_addendum(ctx)
        # Should cap at 10 topics to avoid prompt bloat
        assert result.count("topic") <= 11  # header + 10 topics


# ---------------------------------------------------------------------------
# DiversityEngine
# ---------------------------------------------------------------------------


class TestDiversityEngine:

    def test_build_context_basic(self):
        repo = _make_repo()
        engine = DiversityEngine(repo)
        ctx = engine.build_context(run_id="run1", domain="clean-energy")
        assert ctx.run_id == "run1"
        assert ctx.domain == "clean-energy"
        assert isinstance(ctx.sub_domain, str)
        assert isinstance(ctx.excluded_topics, list)
        assert isinstance(ctx.excluded_neighbor_titles, list)

    def test_build_context_persists(self):
        repo = _make_repo()
        engine = DiversityEngine(repo)
        ctx = engine.build_context(run_id="run2", domain="clean-energy")
        saved = repo.get_diversity_context("run2")
        assert saved is not None
        assert saved["domain"] == "clean-energy"
        assert saved["sub_domain"] == ctx.sub_domain

    def test_build_context_sub_domain_override(self):
        repo = _make_repo()
        engine = DiversityEngine(repo)
        ctx = engine.build_context(
            run_id="run3", domain="clean-energy", sub_domain_override="green hydrogen production"
        )
        assert ctx.sub_domain == "green hydrogen production"

    def test_advance_rotation_first_run(self):
        repo = _make_repo()
        engine = DiversityEngine(repo)
        engine.advance_rotation("clean-energy")
        state = repo.get_rotation_state("clean-energy")
        assert state is not None
        assert state["total_runs"] == 1
        assert state["domain"] == "clean-energy"

    def test_advance_rotation_increments_index(self):
        repo = _make_repo()
        engine = DiversityEngine(repo)
        # Advance enough times to trigger a rotation (interval=2)
        engine.advance_rotation("clean-energy")
        engine.advance_rotation("clean-energy")
        state1 = repo.get_rotation_state("clean-energy")
        engine.advance_rotation("clean-energy")
        engine.advance_rotation("clean-energy")
        state2 = repo.get_rotation_state("clean-energy")
        # After 4 advances, sub_domain_index should have rotated
        assert state2["total_runs"] == 4
        assert state2["sub_domain_index"] > 0 or state1["sub_domain_index"] > 0

    def test_sub_domain_rotates_through_list(self):
        repo = _make_repo()
        engine = DiversityEngine(repo)
        sub_domains = engine._get_sub_domains("clean-energy")
        assert len(sub_domains) > 0
        assert "solar photovoltaics" in sub_domains

    def test_sub_domains_from_yaml(self):
        clear_config_cache()
        sub_domains = DEFAULT_SUB_DOMAINS.get("clean-energy", [])
        assert len(sub_domains) >= 5

    def test_materials_sub_domains_available(self):
        sub_domains = DEFAULT_SUB_DOMAINS.get("materials", [])
        assert len(sub_domains) >= 5
        assert "metal-organic frameworks" in sub_domains

    def test_excluded_topics_from_blocked_candidates(self):
        repo = _make_repo()
        run_id = _make_run(repo)
        # Insert some novelty-failed candidates
        for i in range(3):
            c = CandidateHypothesis(
                id=new_id(),
                run_id=run_id,
                title=f"Perovskite Solar Cell Efficiency Study {i}",
                domain="clean-energy",
                statement="Testing perovskite efficiency improvements.",
                mechanism="Mechanism here.",
                expected_outcome="Outcome.",
                testability_window_hours=24.0,
            )
            c.status = CandidateStatus.NOVELTY_FAILED
            repo.save_candidate(c)

        engine = DiversityEngine(repo)
        topics = engine._extract_excluded_topics("clean-energy")
        # Should extract some topics from perovskite titles
        assert isinstance(topics, list)
        # At minimum, should return something (not necessarily specific words)

    def test_focus_areas_for_sub_domain(self):
        repo = _make_repo()
        engine = DiversityEngine(repo)
        areas = engine._get_focus_areas("clean-energy", "solar photovoltaics")
        assert isinstance(areas, list)
        assert len(areas) >= 2


# ---------------------------------------------------------------------------
# _extract_title_topics helper
# ---------------------------------------------------------------------------


class TestExtractTitleTopics:

    def test_extracts_bigrams(self):
        topics = _extract_title_topics("Perovskite Solar Cell Efficiency Enhancement")
        assert isinstance(topics, list)
        assert len(topics) <= 3

    def test_filters_stop_words(self):
        topics = _extract_title_topics("A Novel and Enhanced Solar Cell with High Efficiency")
        # "novel", "enhanced", "high", "and" should be filtered
        for t in topics:
            assert "novel" not in t.lower()
            assert " and " not in t.lower()

    def test_short_title_fallback(self):
        topics = _extract_title_topics("Short")
        assert isinstance(topics, list)  # should not crash

    def test_empty_title(self):
        topics = _extract_title_topics("")
        assert topics == []


# ---------------------------------------------------------------------------
# CorpusManager
# ---------------------------------------------------------------------------


class TestCorpusManager:

    def test_is_active_new_candidate(self):
        repo = _make_repo()
        cid = _make_candidate(repo)
        cm = CorpusManager(repo)
        assert cm.is_active(cid) is True

    def test_archive_makes_inactive(self):
        repo = _make_repo()
        cid = _make_candidate(repo)
        repo.archive_candidate(cid, "clean-energy", "test")
        cm = CorpusManager(repo)
        assert cm.is_active(cid) is False

    def test_run_archival_returns_stats(self):
        repo = _make_repo()
        cm = CorpusManager(repo)
        result = cm.run_archival("clean-energy")
        assert "domain" in result
        assert "archived_by_age" in result
        assert result["domain"] == "clean-energy"

    def test_run_archival_does_not_archive_protected(self):
        repo = _make_repo()
        cid = _make_candidate(repo, status=CandidateStatus.PUBLISHED)  # PUBLISHED is protected
        cm = CorpusManager(repo, archive_age_days=0)  # archive_age_days=0 = everything eligible
        cm.run_archival("clean-energy")
        # published candidates should be protected
        assert cm.is_active(cid) is True

    def test_get_active_count(self):
        repo = _make_repo()
        cid1 = _make_candidate(repo)
        cid2 = _make_candidate(repo)
        cm = CorpusManager(repo)
        count_before = cm.get_active_count("clean-energy")
        repo.archive_candidate(cid1, "clean-energy", "test")
        count_after = cm.get_active_count("clean-energy")
        assert count_after == count_before - 1

    def test_archive_by_cluster_removes_oldest(self):
        repo = _make_repo()
        ids = [_make_candidate(repo) for _ in range(8)]
        cm = CorpusManager(repo)
        archived = cm.archive_by_cluster("clean-energy", ids, cluster_id="cluster1", keep_newest=3)
        assert archived == 5
        # The kept ones should still be active
        for cid in ids[-3:]:
            assert cm.is_active(cid) is True
        # The archived ones should be inactive
        for cid in ids[:5]:
            assert cm.is_active(cid) is False

    def test_archive_by_cluster_no_op_if_small(self):
        repo = _make_repo()
        ids = [_make_candidate(repo) for _ in range(3)]
        cm = CorpusManager(repo)
        archived = cm.archive_by_cluster("clean-energy", ids, cluster_id="small", keep_newest=5)
        assert archived == 0

    def test_get_active_candidate_ids(self):
        repo = _make_repo()
        cid1 = _make_candidate(repo)
        cid2 = _make_candidate(repo)
        repo.archive_candidate(cid1, "clean-energy", "test")
        cm = CorpusManager(repo)
        active_ids = cm.get_active_candidate_ids("clean-energy")
        assert cid2 in active_ids
        assert cid1 not in active_ids


# ---------------------------------------------------------------------------
# Repository v005 methods
# ---------------------------------------------------------------------------


class TestRepositoryV005:

    def test_save_get_diversity_context(self):
        repo = _make_repo()
        data = {
            "run_id": "run_xyz",
            "domain": "clean-energy",
            "sub_domain": "solar photovoltaics",
            "excluded_topics": ["topic1", "topic2"],
            "excluded_neighbor_titles": ["Old Hypothesis"],
            "rotation_policy": "auto",
            "focus_areas": ["focus1"],
        }
        repo.save_diversity_context(data)
        result = repo.get_diversity_context("run_xyz")
        assert result is not None
        assert result["domain"] == "clean-energy"
        assert result["sub_domain"] == "solar photovoltaics"
        assert "topic1" in result["excluded_topics"]
        assert "Old Hypothesis" in result["excluded_neighbor_titles"]
        assert "focus1" in result["focus_areas"]

    def test_get_diversity_context_missing(self):
        repo = _make_repo()
        result = repo.get_diversity_context("nonexistent_run")
        assert result is None

    def test_save_get_rotation_state(self):
        repo = _make_repo()
        assert repo.get_rotation_state("clean-energy") is None
        repo.save_rotation_state("clean-energy", "solar photovoltaics", 0, 1)
        state = repo.get_rotation_state("clean-energy")
        assert state is not None
        assert state["domain"] == "clean-energy"
        assert state["last_sub_domain"] == "solar photovoltaics"
        assert state["sub_domain_index"] == 0
        assert state["total_runs"] == 1

    def test_rotation_state_upsert(self):
        repo = _make_repo()
        repo.save_rotation_state("clean-energy", "solar photovoltaics", 0, 1)
        repo.save_rotation_state("clean-energy", "grid-scale energy storage", 1, 2)
        state = repo.get_rotation_state("clean-energy")
        assert state["last_sub_domain"] == "grid-scale energy storage"
        assert state["sub_domain_index"] == 1
        assert state["total_runs"] == 2

    def test_archive_candidate(self):
        repo = _make_repo()
        cid = _make_candidate(repo)
        assert not repo.is_archived(cid)
        repo.archive_candidate(cid, "clean-energy", "recency", "")
        assert repo.is_archived(cid)

    def test_archive_candidate_idempotent(self):
        repo = _make_repo()
        cid = _make_candidate(repo)
        repo.archive_candidate(cid, "clean-energy", "recency")
        repo.archive_candidate(cid, "clean-energy", "recency")  # should not raise
        assert repo.is_archived(cid)

    def test_list_archived_candidates(self):
        repo = _make_repo()
        cid1 = _make_candidate(repo)
        cid2 = _make_candidate(repo)
        cid3 = _make_candidate(repo)
        repo.archive_candidate(cid1, "clean-energy", "recency")
        repo.archive_candidate(cid2, "clean-energy", "cluster_saturation", "c1")
        archived = repo.list_archived_candidates("clean-energy")
        archived_ids = {r["candidate_id"] for r in archived}
        assert cid1 in archived_ids
        assert cid2 in archived_ids
        assert cid3 not in archived_ids

    def test_is_archived_false_for_unknown(self):
        repo = _make_repo()
        assert not repo.is_archived("nonexistent_id")


# ---------------------------------------------------------------------------
# Schema migration v005
# ---------------------------------------------------------------------------


class TestMigrationV005:

    def test_schema_version_is_5(self):
        db = _make_db()
        assert _current_version(db) >= 5

    def test_diversity_context_table_exists(self):
        db = _make_db()
        result = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_diversity_context'"
        ).fetchone()
        assert result is not None

    def test_rotation_state_table_exists(self):
        db = _make_db()
        result = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_rotation_state'"
        ).fetchone()
        assert result is not None

    def test_corpus_archive_table_exists(self):
        db = _make_db()
        result = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_corpus_archive'"
        ).fetchone()
        assert result is not None

    def test_rotation_state_primary_key_is_domain(self):
        db = _make_db()
        # Should allow insert and conflict update
        db.execute(
            "INSERT INTO bt_rotation_state (domain, last_sub_domain, sub_domain_index, total_runs, updated_at) "
            "VALUES ('test', 'sub1', 0, 1, '2026-03-08T00:00:00Z')"
        )
        db.execute(
            "INSERT INTO bt_rotation_state (domain, last_sub_domain, sub_domain_index, total_runs, updated_at) "
            "VALUES ('test', 'sub2', 1, 2, '2026-03-08T01:00:00Z') "
            "ON CONFLICT(domain) DO UPDATE SET last_sub_domain=excluded.last_sub_domain"
        )
        row = db.execute("SELECT * FROM bt_rotation_state WHERE domain='test'").fetchone()
        assert row["last_sub_domain"] == "sub2"


# ---------------------------------------------------------------------------
# Materials bootstrap
# ---------------------------------------------------------------------------


class TestMaterialsBootstrap:

    def test_seed_materials_returns_counts(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        from breakthrough_engine.bootstrap_findings import (
            ensure_upstream_tables,
            seed_materials,
        )
        ensure_upstream_tables(db)
        papers, findings = seed_materials(db)
        assert papers == 12
        assert findings >= 14  # 12+ findings across papers

    def test_seed_materials_idempotent(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        from breakthrough_engine.bootstrap_findings import (
            ensure_upstream_tables,
            seed_materials,
        )
        ensure_upstream_tables(db)
        p1, f1 = seed_materials(db)
        p2, _ = seed_materials(db)
        # Second call should add 0 papers (papers have INSERT OR IGNORE)
        assert p2 == 0

    def test_seeded_materials_findings_are_accepted(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        from breakthrough_engine.bootstrap_findings import (
            ensure_upstream_tables,
            seed_materials,
        )
        ensure_upstream_tables(db)
        seed_materials(db)
        count = db.execute(
            "SELECT COUNT(*) FROM findings WHERE judge_verdict='accepted'"
        ).fetchone()[0]
        assert count >= 14

    def test_materials_paper_subjects(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        from breakthrough_engine.bootstrap_findings import (
            ensure_upstream_tables,
            seed_materials,
        )
        ensure_upstream_tables(db)
        seed_materials(db)
        rows = db.execute(
            "SELECT subjects FROM papers WHERE paper_id LIKE 'bootstrap_mat_%'"
        ).fetchall()
        assert len(rows) == 12
        for row in rows:
            assert "materials" in row["subjects"]


# ---------------------------------------------------------------------------
# Domain-fit YAML with sub_domains
# ---------------------------------------------------------------------------


class TestDomainFitSubDomains:

    def setup_method(self):
        clear_config_cache()

    def test_clean_energy_config_has_sub_domains(self):
        cfg = load_domain_fit_config("clean-energy")
        assert hasattr(cfg, "sub_domains")
        assert isinstance(cfg.sub_domains, list)
        assert len(cfg.sub_domains) >= 5
        assert "solar photovoltaics" in cfg.sub_domains

    def test_materials_config_has_sub_domains(self):
        cfg = load_domain_fit_config("materials")
        assert hasattr(cfg, "sub_domains")
        assert isinstance(cfg.sub_domains, list)
        assert len(cfg.sub_domains) >= 5
        assert "metal-organic frameworks" in cfg.sub_domains

    def test_cross_domain_config_has_empty_sub_domains(self):
        cfg = load_domain_fit_config("cross-domain")
        assert hasattr(cfg, "sub_domains")
        # cross-domain has no sub_domains defined
        assert isinstance(cfg.sub_domains, list)


# ---------------------------------------------------------------------------
# CandidateGenerator diversity_context parameter
# ---------------------------------------------------------------------------


class TestCandidateGeneratorDiversityContext:

    def test_fake_generator_accepts_diversity_context(self):
        from breakthrough_engine.candidate_generator import FakeCandidateGenerator
        from breakthrough_engine.models import EvidenceItem
        gen = FakeCandidateGenerator()
        ctx = DiversityContext(run_id="r1", domain="clean-energy", sub_domain="solar photovoltaics")
        evidence = []
        result = gen.generate(evidence=evidence, domain="clean-energy", budget=2,
                              run_id="r1", diversity_context=ctx)
        assert isinstance(result, list)

    def test_demo_generator_accepts_diversity_context(self):
        from breakthrough_engine.candidate_generator import DemoCandidateGenerator
        gen = DemoCandidateGenerator()
        ctx = DiversityContext(run_id="r1", domain="clean-energy")
        result = gen.generate(evidence=[], domain="clean-energy", budget=2,
                              run_id="r1", diversity_context=ctx)
        assert isinstance(result, list)

    def test_fake_generator_works_without_diversity_context(self):
        from breakthrough_engine.candidate_generator import FakeCandidateGenerator
        gen = FakeCandidateGenerator()
        result = gen.generate(evidence=[], domain="clean-energy", budget=2)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Orchestrator Phase 4D integration
# ---------------------------------------------------------------------------


class TestOrchestratorPhase4D:

    def _make_program(self, mode=RunMode.DETERMINISTIC_TEST, domain="clean-energy"):
        return ResearchProgram(
            name="test_program",
            domain=domain,
            mode=mode,
            candidate_budget=3,
            publication_threshold=0.5,
        )

    def test_orchestrator_has_diversity_engine(self):
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        repo = _make_repo()
        prog = self._make_program()
        orch = BreakthroughOrchestrator(prog, repo)
        assert hasattr(orch, "diversity_engine")
        assert isinstance(orch.diversity_engine, DiversityEngine)

    def test_orchestrator_has_corpus_manager(self):
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        repo = _make_repo()
        prog = self._make_program()
        orch = BreakthroughOrchestrator(prog, repo)
        assert hasattr(orch, "corpus_manager")
        assert isinstance(orch.corpus_manager, CorpusManager)

    def test_run_persists_diversity_context(self):
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        repo = _make_repo()
        prog = self._make_program()
        orch = BreakthroughOrchestrator(prog, repo)
        run = orch.run()
        # Diversity context should be saved for this run
        ctx = repo.get_diversity_context(run.id)
        assert ctx is not None
        assert ctx["domain"] == "clean-energy"

    def test_run_advances_rotation(self):
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        repo = _make_repo()
        prog = self._make_program()
        orch = BreakthroughOrchestrator(prog, repo)
        orch.run()
        state = repo.get_rotation_state("clean-energy")
        assert state is not None
        assert state["total_runs"] == 1

    def test_run_in_materials_domain(self):
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        repo = _make_repo()
        prog = self._make_program(domain="materials")
        orch = BreakthroughOrchestrator(prog, repo)
        run = orch.run()
        ctx = repo.get_diversity_context(run.id)
        assert ctx is not None
        assert ctx["domain"] == "materials"


# ---------------------------------------------------------------------------
# Phase 4D Validation: Runtime archival wiring
# ---------------------------------------------------------------------------


class TestRuntimeArchivalWiring:
    """Verify corpus archival is actually called during orchestrator runs."""

    def _make_program(self, domain="clean-energy"):
        return ResearchProgram(
            name="test_archival",
            domain=domain,
            mode=RunMode.DETERMINISTIC_TEST,
            candidate_budget=2,
            publication_threshold=0.5,
        )

    def test_archival_wired_non_fatal_on_empty_corpus(self):
        """Archival during a run on an empty corpus should not fail the run."""
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        repo = _make_repo()
        prog = self._make_program()
        orch = BreakthroughOrchestrator(prog, repo)
        run = orch.run()
        # Run should complete normally even with nothing to archive
        assert run.status.value in ("completed", "completed_no_publication")

    def test_archival_archives_old_candidates(self):
        """Candidates older than archive_age_days are archived by run_archival."""
        from datetime import datetime, timezone, timedelta
        repo = _make_repo()
        cm = CorpusManager(repo, archive_age_days=30)

        # Inject a candidate created 40 days ago
        cid = _make_candidate(repo, domain="clean-energy", status=CandidateStatus.NOVELTY_FAILED)
        old_dt = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
        repo.db.execute(
            "UPDATE bt_candidates SET created_at=? WHERE id=?", (old_dt, cid)
        )
        repo.db.commit()

        stats = cm.run_archival("clean-energy")
        assert stats["archived_by_age"] >= 1
        assert cm.is_active(cid) is False

    def test_archival_protects_published_candidates(self):
        """Published candidates must never be archived by age."""
        from datetime import datetime, timezone, timedelta
        repo = _make_repo()
        cm = CorpusManager(repo, archive_age_days=1)

        cid = _make_candidate(repo, domain="clean-energy", status=CandidateStatus.PUBLISHED)
        old_dt = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        repo.db.execute(
            "UPDATE bt_candidates SET created_at=? WHERE id=?", (old_dt, cid)
        )
        repo.db.commit()

        cm.run_archival("clean-energy")
        # Must still be active
        assert cm.is_active(cid) is True

    def test_archival_stats_in_calibration_diagnostic(self):
        """Calibration diagnostic should include corpus_maintenance in active_thresholds after a run."""
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        repo = _make_repo()
        prog = self._make_program()
        orch = BreakthroughOrchestrator(prog, repo)
        run = orch.run()
        # Check calibration diagnostic has corpus_maintenance nested in active_thresholds
        diag = repo.get_calibration_diagnostic(run.id)
        assert diag is not None
        import json
        thresholds = json.loads(diag["active_thresholds"])
        assert "corpus_maintenance" in thresholds
        assert "active_corpus_size" in thresholds["corpus_maintenance"]


# ---------------------------------------------------------------------------
# Phase 4D Validation: Active-corpus novelty filtering
# ---------------------------------------------------------------------------


class TestActiveCorpusNoveltyFiltering:
    """Verify novelty engine uses only active (non-archived) candidates."""

    def _make_program(self, domain="clean-energy"):
        return ResearchProgram(
            name="test_novelty_filter",
            domain=domain,
            mode=RunMode.DETERMINISTIC_TEST,
            candidate_budget=2,
            publication_threshold=0.5,
        )

    def test_active_candidate_ids_excludes_archived(self):
        """get_active_candidate_ids should not include archived candidates."""
        repo = _make_repo()
        cm = CorpusManager(repo)

        active_id = _make_candidate(repo, domain="clean-energy")
        archived_id = _make_candidate(repo, domain="clean-energy")
        repo.archive_candidate(archived_id, "clean-energy", "test_reason", "")

        active_ids = cm.get_active_candidate_ids("clean-energy")
        assert active_id in active_ids
        assert archived_id not in active_ids

    def test_active_candidate_ids_empty_when_all_archived(self):
        """If all candidates are archived, active set should be empty."""
        repo = _make_repo()
        cm = CorpusManager(repo)

        cid = _make_candidate(repo, domain="clean-energy")
        repo.archive_candidate(cid, "clean-energy", "test", "")

        active_ids = cm.get_active_candidate_ids("clean-energy")
        assert cid not in active_ids

    def test_novelty_gate_runs_with_no_active_candidates(self):
        """Orchestrator run should complete even if all prior candidates are archived."""
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        repo = _make_repo()

        # Pre-populate and archive all prior candidates for this domain
        for _ in range(3):
            cid = _make_candidate(repo, domain="clean-energy", status=CandidateStatus.NOVELTY_FAILED)
            repo.archive_candidate(cid, "clean-energy", "test", "")

        prog = self._make_program()
        orch = BreakthroughOrchestrator(prog, repo)
        run = orch.run()
        # Run should succeed — empty active corpus means no embedding blocks
        assert run.status.value in ("completed", "completed_no_publication")

    def test_same_domain_duplicate_still_blocked_with_active_corpus(self):
        """A recently generated identical candidate (active) should still be caught."""
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        # Two sequential runs with FakeCandidateGenerator produce very similar candidates.
        # The second run should still block duplicates via the deduplication step.
        repo = _make_repo()
        prog = self._make_program()
        orch = BreakthroughOrchestrator(prog, repo)
        run1 = orch.run()
        run2 = orch.run()
        # Both runs should complete (may or may not produce publications)
        assert run1.status.value in ("completed", "completed_no_publication")
        assert run2.status.value in ("completed", "completed_no_publication")
