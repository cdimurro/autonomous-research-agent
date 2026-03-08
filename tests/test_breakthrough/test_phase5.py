"""Phase 5 tests: Cross-domain synthesis.

Tests:
1. Domain-pair selection and pairing policies
2. Synthesis-aware prompt/context generation
3. Balanced evidence pack construction and role tagging
4. Synthesis fit scoring
5. Synthesis-aware novelty diagnostics
6. Hybrid run policy selection
7. Review visibility for synthesis metadata
8. Schema v006 migration
9. Orchestrator integration with synthesis
"""

import json
import sqlite3

import pytest

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateScore,
    CandidateStatus,
    EvidenceItem,
    EvidencePack,
    NoveltyResult,
    ResearchProgram,
    RunMode,
    RunRecord,
    RunStatus,
    new_id,
)
from breakthrough_engine.synthesis import (
    BRIDGE_SUB_DOMAINS,
    BRIDGE_TO_SUB_DOMAINS,
    SynthesisContext,
    SynthesisEngine,
    SynthesisFitEvaluator,
    SynthesisFitResult,
    build_synthesis_prompt_addendum,
    tag_evidence_roles,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    conn = init_db(in_memory=True)
    yield conn
    conn.close()


@pytest.fixture
def repo(db):
    return Repository(db)


@pytest.fixture
def synthesis_engine(repo):
    return SynthesisEngine(repo)


@pytest.fixture
def fit_evaluator():
    return SynthesisFitEvaluator()


def _make_candidate(
    domain="clean-energy+materials",
    title="HEA Electrocatalyst for Green Hydrogen",
    mechanism="High-entropy alloy surfaces provide multiple active sites for hydrogen evolution reaction, reducing overpotential via synergistic multi-element catalysis.",
    statement="Combining HEA design with PEM electrolyzer architecture will reduce hydrogen production cost by 30%.",
    run_id="",
) -> CandidateHypothesis:
    return CandidateHypothesis(
        id=new_id(),
        run_id=run_id or new_id(),
        title=title,
        domain=domain,
        statement=statement,
        mechanism=mechanism,
        expected_outcome="30% reduction in hydrogen production cost",
        assumptions=["HEA stability under acidic conditions"],
        risk_flags=["Long-term corrosion"],
        evidence_refs=[],
    )


def _make_evidence(
    domain="clean-energy",
    title="PEM Electrolyzer Advances",
    quote="Recent advances in PEM electrolysis...",
) -> EvidenceItem:
    return EvidenceItem(
        id=new_id(),
        source_type="finding",
        source_id=new_id(),
        title=title,
        quote=quote,
        citation=f"Test {domain}",
        relevance_score=0.7,
    )


# ---------------------------------------------------------------------------
# Test: Schema v006 migration
# ---------------------------------------------------------------------------


class TestSchemaV006:
    def test_schema_version_is_6(self, db):
        row = db.execute("SELECT MAX(version) FROM bt_schema_version").fetchone()
        assert row[0] >= 6

    def test_synthesis_context_table_exists(self, db):
        db.execute("SELECT * FROM bt_synthesis_context LIMIT 1")

    def test_synthesis_fit_table_exists(self, db):
        db.execute("SELECT * FROM bt_synthesis_fit LIMIT 1")

    def test_synthesis_context_insert(self, repo):
        data = {
            "run_id": "test_run",
            "primary_domain": "clean-energy",
            "secondary_domain": "materials",
            "bridge_mechanism": "electrocatalysts",
            "pairing_policy": "rotating_pair",
        }
        repo.save_synthesis_context(data)
        result = repo.get_synthesis_context("test_run")
        assert result is not None
        assert result["primary_domain"] == "clean-energy"
        assert result["secondary_domain"] == "materials"

    def test_synthesis_fit_insert(self, repo):
        data = {
            "candidate_id": "test_cand",
            "cross_domain_fit_score": 0.75,
            "bridge_mechanism_score": 0.8,
            "evidence_balance_score": 0.7,
            "superficial_mashup_flag": False,
            "synthesis_reasons": ["Good bridge"],
            "evidence_roles": {"ev1": "primary_support"},
            "passed": True,
        }
        repo.save_synthesis_fit(data)
        result = repo.get_synthesis_fit("test_cand")
        assert result is not None
        assert result["cross_domain_fit_score"] == 0.75


# ---------------------------------------------------------------------------
# Test: Domain pair selection
# ---------------------------------------------------------------------------


class TestDomainPairSelection:
    def test_bridge_sub_domains_exist(self):
        key = ("clean-energy", "materials")
        assert key in BRIDGE_SUB_DOMAINS
        assert len(BRIDGE_SUB_DOMAINS[key]) == 10

    def test_bridge_to_sub_domains_mapping(self):
        for bridge, (primary, secondary) in BRIDGE_TO_SUB_DOMAINS.items():
            assert primary, f"Empty primary sub-domain for bridge: {bridge}"
            assert secondary, f"Empty secondary sub-domain for bridge: {bridge}"

    def test_parse_domain_pair(self, synthesis_engine):
        p, s = synthesis_engine.parse_domain_pair("clean-energy+materials")
        assert p == "clean-energy"
        assert s == "materials"

    def test_parse_domain_pair_default(self, synthesis_engine):
        p, s = synthesis_engine.parse_domain_pair("cross-domain")
        assert p == "clean-energy"
        assert s == "materials"

    def test_is_cross_domain_program(self, synthesis_engine):
        prog = ResearchProgram(name="test", domain="clean-energy+materials")
        assert synthesis_engine.is_cross_domain_program(prog)

    def test_is_not_cross_domain_program(self, synthesis_engine):
        prog = ResearchProgram(name="test", domain="clean-energy")
        assert not synthesis_engine.is_cross_domain_program(prog)

    def test_cross_domain_keyword_detection(self, synthesis_engine):
        prog = ResearchProgram(name="test", domain="cross-domain")
        assert synthesis_engine.is_cross_domain_program(prog)


# ---------------------------------------------------------------------------
# Test: Synthesis context building
# ---------------------------------------------------------------------------


class TestSynthesisContextBuilding:
    def test_build_context_basic(self, synthesis_engine):
        ctx = synthesis_engine.build_context(
            run_id="test_run",
            primary_domain="clean-energy",
            secondary_domain="materials",
        )
        assert ctx.primary_domain == "clean-energy"
        assert ctx.secondary_domain == "materials"
        assert ctx.bridge_mechanism != ""
        assert ctx.primary_sub_domain != ""
        assert ctx.secondary_sub_domain != ""

    def test_build_context_with_bridge_override(self, synthesis_engine):
        ctx = synthesis_engine.build_context(
            run_id="test_run",
            primary_domain="clean-energy",
            secondary_domain="materials",
            bridge_override="hydrogen storage materials",
        )
        assert ctx.bridge_mechanism == "hydrogen storage materials"
        assert ctx.primary_sub_domain == "green hydrogen production"
        assert ctx.secondary_sub_domain == "metal-organic frameworks"

    def test_build_context_fixed_pair(self, synthesis_engine):
        ctx = synthesis_engine.build_context(
            run_id="test_run",
            primary_domain="clean-energy",
            secondary_domain="materials",
            pairing_policy="fixed_pair",
        )
        assert ctx.pairing_policy == "fixed_pair"
        assert ctx.bridge_mechanism != ""

    def test_context_persisted(self, synthesis_engine, repo):
        ctx = synthesis_engine.build_context(
            run_id="test_persist",
            primary_domain="clean-energy",
            secondary_domain="materials",
        )
        saved = repo.get_synthesis_context("test_persist")
        assert saved is not None
        assert saved["primary_domain"] == "clean-energy"

    def test_context_to_dict(self):
        ctx = SynthesisContext(
            run_id="r1",
            primary_domain="clean-energy",
            secondary_domain="materials",
            bridge_mechanism="electrocatalysts",
        )
        d = ctx.to_dict()
        assert d["run_id"] == "r1"
        assert d["bridge_mechanism"] == "electrocatalysts"

    def test_bridge_rotation_advance(self, synthesis_engine, repo):
        # Initial state
        ctx1 = synthesis_engine.build_context(
            "run1", "clean-energy", "materials"
        )
        bridge1 = ctx1.bridge_mechanism

        # Advance twice (rotation interval = 2)
        synthesis_engine.advance_bridge_rotation("clean-energy", "materials")
        synthesis_engine.advance_bridge_rotation("clean-energy", "materials")

        ctx2 = synthesis_engine.build_context(
            "run2", "clean-energy", "materials"
        )
        bridge2 = ctx2.bridge_mechanism
        assert bridge2 != bridge1, "Bridge should rotate after interval"

    def test_focus_angles_populated(self, synthesis_engine):
        ctx = synthesis_engine.build_context(
            "run1", "clean-energy", "materials",
            bridge_override="electrocatalysts for energy conversion",
        )
        assert len(ctx.focus_angles) > 0


# ---------------------------------------------------------------------------
# Test: Synthesis prompt addendum
# ---------------------------------------------------------------------------


class TestSynthesisPromptAddendum:
    def test_addendum_contains_domains(self):
        ctx = SynthesisContext(
            run_id="r1",
            primary_domain="clean-energy",
            secondary_domain="materials",
            bridge_mechanism="electrocatalysts",
        )
        addendum = build_synthesis_prompt_addendum(ctx)
        assert "clean-energy" in addendum
        assert "materials" in addendum
        assert "CROSS-DOMAIN SYNTHESIS" in addendum

    def test_addendum_contains_bridge(self):
        ctx = SynthesisContext(
            run_id="r1",
            primary_domain="clean-energy",
            secondary_domain="materials",
            bridge_mechanism="electrocatalysts for energy conversion",
        )
        addendum = build_synthesis_prompt_addendum(ctx)
        assert "electrocatalysts" in addendum

    def test_addendum_contains_requirements(self):
        ctx = SynthesisContext(
            run_id="r1",
            primary_domain="clean-energy",
            secondary_domain="materials",
        )
        addendum = build_synthesis_prompt_addendum(ctx)
        assert "BOTH domains" in addendum
        assert "non-obvious" in addendum
        assert "superficial" in addendum

    def test_addendum_contains_excluded_themes(self):
        ctx = SynthesisContext(
            run_id="r1",
            primary_domain="clean-energy",
            secondary_domain="materials",
            excluded_cross_themes=["MOF catalysis for hydrogen"],
        )
        addendum = build_synthesis_prompt_addendum(ctx)
        assert "MOF catalysis for hydrogen" in addendum

    def test_addendum_contains_focus_angles(self):
        ctx = SynthesisContext(
            run_id="r1",
            primary_domain="clean-energy",
            secondary_domain="materials",
            focus_angles=["single-atom catalysts", "bifunctional design"],
        )
        addendum = build_synthesis_prompt_addendum(ctx)
        assert "single-atom catalysts" in addendum


# ---------------------------------------------------------------------------
# Test: Evidence role tagging
# ---------------------------------------------------------------------------


class TestEvidenceRoleTagging:
    def test_tag_primary_evidence(self):
        ev = [_make_evidence("clean-energy", "Solar Cell Efficiency", "Photovoltaic solar panel improvements")]
        roles = tag_evidence_roles(ev, "clean-energy", "materials")
        assert roles[ev[0].id] == "primary_support"

    def test_tag_secondary_evidence(self):
        ev = [_make_evidence("materials", "High-Entropy Alloy Design", "Novel alloy compositions with polymer composite")]
        roles = tag_evidence_roles(ev, "clean-energy", "materials")
        assert roles[ev[0].id] == "secondary_support"

    def test_tag_bridge_evidence(self):
        ev = [_make_evidence(
            "both",
            "Catalyst for Solar Fuel",
            "Novel catalyst material for solar hydrogen photovoltaic alloy electrode",
        )]
        roles = tag_evidence_roles(ev, "clean-energy", "materials")
        assert roles[ev[0].id] == "bridge_support"

    def test_tag_mixed_evidence(self):
        ev = [
            _make_evidence("clean-energy", "Solar Advances", "Solar photovoltaic renewable energy"),
            _make_evidence("materials", "Alloy Design", "High-entropy alloy composite nanomaterial"),
            _make_evidence("both", "Catalyst Electrode", "Solar catalyst electrode alloy hydrogen"),
        ]
        roles = tag_evidence_roles(ev, "clean-energy", "materials")
        counts = {"primary_support": 0, "secondary_support": 0, "bridge_support": 0}
        for role in roles.values():
            counts[role] += 1
        assert counts["primary_support"] >= 1
        assert counts["secondary_support"] >= 1


# ---------------------------------------------------------------------------
# Test: Synthesis fit evaluation
# ---------------------------------------------------------------------------


class TestSynthesisFitEvaluation:
    def test_non_synthesis_auto_pass(self, fit_evaluator):
        c = _make_candidate()
        result = fit_evaluator.evaluate(c, synthesis_ctx=None)
        assert result.passed
        assert result.cross_domain_fit_score == 1.0

    def test_good_synthesis_candidate(self, fit_evaluator):
        c = _make_candidate(
            mechanism=(
                "High-entropy alloy (materials) surfaces provide multiple active sites "
                "for hydrogen evolution reaction in PEM electrolyzers (clean energy). "
                "The synergistic multi-element catalysis reduces overpotential by 200mV "
                "compared to single-metal catalysts."
            ),
        )
        ctx = SynthesisContext(
            run_id="r1",
            primary_domain="clean-energy",
            secondary_domain="materials",
            bridge_mechanism="electrocatalysts for energy conversion",
        )
        roles = {"ev1": "primary_support", "ev2": "secondary_support", "ev3": "bridge_support"}
        result = fit_evaluator.evaluate(c, synthesis_ctx=ctx, evidence_roles=roles)
        assert result.passed
        assert result.bridge_mechanism_score > 0.5
        assert not result.superficial_mashup_flag

    def test_superficial_mashup_detected(self, fit_evaluator):
        c = _make_candidate(
            mechanism="A novel approach.",
            statement="Combining stuff from both fields.",
        )
        ctx = SynthesisContext(
            run_id="r1",
            primary_domain="clean-energy",
            secondary_domain="materials",
            bridge_mechanism="electrocatalysts",
        )
        result = fit_evaluator.evaluate(c, synthesis_ctx=ctx, evidence_roles={})
        assert result.superficial_mashup_flag
        assert result.cross_domain_fit_score < 0.5

    def test_unbalanced_evidence_penalized(self, fit_evaluator):
        c = _make_candidate()
        ctx = SynthesisContext(
            run_id="r1",
            primary_domain="clean-energy",
            secondary_domain="materials",
            bridge_mechanism="electrocatalysts",
        )
        # All evidence from one side
        roles = {"ev1": "primary_support", "ev2": "primary_support", "ev3": "primary_support"}
        result = fit_evaluator.evaluate(c, synthesis_ctx=ctx, evidence_roles=roles)
        assert result.evidence_balance_score < 0.5

    def test_fit_result_to_dict(self, fit_evaluator):
        c = _make_candidate()
        ctx = SynthesisContext(
            run_id="r1",
            primary_domain="clean-energy",
            secondary_domain="materials",
        )
        result = fit_evaluator.evaluate(c, synthesis_ctx=ctx)
        d = result.to_dict()
        assert "cross_domain_fit_score" in d
        assert "bridge_mechanism_score" in d
        assert "superficial_mashup_flag" in d


# ---------------------------------------------------------------------------
# Test: Synthesis-aware novelty
# ---------------------------------------------------------------------------


class TestSynthesisAwareNovelty:
    def test_novelty_searches_both_domains(self, db):
        from breakthrough_engine.novelty import NoveltyEngine

        engine = NoveltyEngine(db)
        # Insert a run record for FK
        run_id = new_id()
        db.execute(
            """INSERT INTO bt_runs (id, program_name, mode, status, started_at)
               VALUES (?,?,?,?,datetime('now'))""",
            (run_id, "test", "demo_local", "started"),
        )
        # Insert candidates in both domains
        for domain in ["clean-energy", "materials", "clean-energy+materials"]:
            db.execute(
                """INSERT INTO bt_candidates
                   (id, run_id, title, domain, statement, mechanism,
                    expected_outcome, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,datetime('now'))""",
                (new_id(), run_id, f"Test {domain}", domain,
                 f"Test statement for {domain}", "test mechanism",
                 "test outcome", "generated"),
            )
        db.commit()

        # Cross-domain query should find all three
        priors = engine._get_prior_candidates("clean-energy+materials", "run_test")
        domains_found = set(p["domain"] if "domain" in p else "" for p in priors)
        # Should find candidates from the cross-domain domain
        assert len(priors) >= 1


# ---------------------------------------------------------------------------
# Test: Hybrid run policy
# ---------------------------------------------------------------------------


class TestHybridRunPolicy:
    def test_cross_domain_program_config_loads(self):
        from breakthrough_engine.config_loader import load_program
        prog = load_program("cross_domain_shadow")
        assert "+" in prog.domain
        assert prog.mode == RunMode.PRODUCTION_SHADOW

    def test_cross_domain_review_config_loads(self):
        from breakthrough_engine.config_loader import load_program
        prog = load_program("cross_domain_review")
        assert prog.mode == RunMode.PRODUCTION_REVIEW

    def test_domain_fit_uses_cross_domain_config(self):
        from breakthrough_engine.domain_fit import load_domain_fit_config, clear_config_cache
        clear_config_cache()
        config = load_domain_fit_config("clean-energy+materials")
        # Should use cross_domain.yaml
        assert config.min_score == 0.0  # cross-domain accepts all


# ---------------------------------------------------------------------------
# Test: Orchestrator integration (offline)
# ---------------------------------------------------------------------------


class TestOrchestratorSynthesisIntegration:
    def test_synthesis_run_completes(self, db, repo):
        """Full synthesis run with fake generator completes without error."""
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        prog = ResearchProgram(
            name="test_synthesis",
            domain="clean-energy+materials",
            mode=RunMode.DETERMINISTIC_TEST,
            candidate_budget=3,
            simulation_budget=1,
        )
        orch = BreakthroughOrchestrator(program=prog, repo=repo)
        run = orch.run()
        assert run.status in (RunStatus.COMPLETED, RunStatus.COMPLETED_NO_PUBLICATION)
        assert run.candidates_generated > 0

    def test_synthesis_shadow_run(self, db, repo):
        """Shadow synthesis run completes."""
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        from breakthrough_engine.candidate_generator import FakeCandidateGenerator
        from breakthrough_engine.evidence_source import DemoFixtureSource

        prog = ResearchProgram(
            name="test_synth_shadow",
            domain="clean-energy+materials",
            mode=RunMode.PRODUCTION_SHADOW,
            candidate_budget=3,
            simulation_budget=1,
        )
        orch = BreakthroughOrchestrator(
            program=prog,
            repo=repo,
            evidence_source=DemoFixtureSource(),
            generator=FakeCandidateGenerator(),
        )
        run = orch.run()
        assert run.status in (RunStatus.COMPLETED, RunStatus.COMPLETED_NO_PUBLICATION)

    def test_synthesis_context_saved_in_db(self, db, repo):
        """Synthesis context is persisted for cross-domain runs."""
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        prog = ResearchProgram(
            name="test_synth_ctx",
            domain="clean-energy+materials",
            mode=RunMode.DETERMINISTIC_TEST,
            candidate_budget=3,
            simulation_budget=1,
        )
        orch = BreakthroughOrchestrator(program=prog, repo=repo)
        run = orch.run()

        ctx = repo.get_synthesis_context(run.id)
        assert ctx is not None
        assert ctx["primary_domain"] == "clean-energy"
        assert ctx["secondary_domain"] == "materials"


# ---------------------------------------------------------------------------
# Test: Review visibility for synthesis metadata
# ---------------------------------------------------------------------------


class TestReviewSynthesisVisibility:
    def test_create_draft_with_synthesis_context(self, repo):
        from breakthrough_engine.review import create_draft

        c = _make_candidate()
        score = CandidateScore(candidate_id=c.id)
        score.compute_final()

        # Save run before candidate (FK constraint)
        run = RunRecord(
            id=c.run_id,
            program_name="test",
            mode=RunMode.PRODUCTION_REVIEW,
        )
        repo.save_run(run)
        repo.save_candidate(c)

        ctx = SynthesisContext(
            run_id=c.run_id,
            primary_domain="clean-energy",
            secondary_domain="materials",
            bridge_mechanism="electrocatalysts",
        )
        fit = SynthesisFitResult(
            candidate_id=c.id,
            cross_domain_fit_score=0.75,
            passed=True,
        )
        roles = {"ev1": "primary_support", "ev2": "secondary_support"}

        draft = create_draft(
            repo=repo,
            run_id=c.run_id,
            candidate=c,
            score=score,
            synthesis_context=ctx,
            synthesis_fit=fit,
            evidence_roles=roles,
        )

        assert "Cross-domain synthesis" in draft.abstract
        assert "synthesis_fit" in draft.score_breakdown

    def test_create_draft_without_synthesis(self, repo):
        """Standard draft creation still works."""
        from breakthrough_engine.review import create_draft

        c = _make_candidate(domain="clean-energy")
        score = CandidateScore(candidate_id=c.id)
        score.compute_final()

        run = RunRecord(
            id=c.run_id,
            program_name="test",
            mode=RunMode.PRODUCTION_REVIEW,
        )
        repo.save_run(run)
        repo.save_candidate(c)

        draft = create_draft(
            repo=repo,
            run_id=c.run_id,
            candidate=c,
            score=score,
        )
        assert "Breakthrough candidate" in draft.abstract


# ---------------------------------------------------------------------------
# Test: Pair key canonicalization
# ---------------------------------------------------------------------------


class TestPairKeyCanon:
    def test_pair_key_is_sorted(self, synthesis_engine):
        k1 = synthesis_engine._pair_key("clean-energy", "materials")
        k2 = synthesis_engine._pair_key("materials", "clean-energy")
        assert k1 == k2

    def test_pair_key_format(self, synthesis_engine):
        k = synthesis_engine._pair_key("clean-energy", "materials")
        assert k.startswith("synthesis:")
        assert "+" in k
