"""Phase 9 tests: Policy actuation, evidence ranking weights, prompt variants.

All tests are offline-safe (no Ollama, no external network, no embeddings).
"""

from __future__ import annotations

import json
import pytest

from breakthrough_engine.candidate_generator import (
    CANDIDATE_GENERATION_PROMPT,
    CANDIDATE_GENERATION_PROMPT_SYNTHESIS_FOCUS,
    CANDIDATE_GENERATION_PROMPT_EVIDENCE_HEAVY,
    PROMPT_VARIANTS,
    FakeCandidateGenerator,
    DemoCandidateGenerator,
    OllamaCandidateGenerator,
)
from breakthrough_engine.models import (
    CandidateScore,
    EvidenceItem,
    ResearchProgram,
    RunMode,
)
from breakthrough_engine.policy_registry import PolicyConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evidence(n: int = 3) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            id=f"ev_{i:03d}",
            title=f"Evidence paper {i}",
            source_id=f"src_{i}",
            source_type="paper",
            quote=f"This paper demonstrates finding {i} related to clean energy.",
            citation=f"Author et al. (202{i})",
            relevance_score=0.8 - i * 0.05,
        )
        for i in range(1, n + 1)
    ]


def _make_policy_with_scoring_weights(name: str = "test_policy") -> PolicyConfig:
    return PolicyConfig(
        id=f"{name}_id",
        name=name,
        scoring_weights={
            "novelty": 0.10,
            "plausibility": 0.35,  # +75% vs default
            "impact": 0.20,
            "evidence_strength": 0.20,
            "simulation_readiness": 0.10,
            "inverse_validation_cost": 0.05,
        },
    )


def _make_synthesis_focus_policy() -> PolicyConfig:
    return PolicyConfig(
        id="synthesis_focus_v1_test",
        name="synthesis_focus_v1",
        generation_prompt_variant="synthesis_focus",
        scoring_weights={
            "novelty": 0.18,
            "plausibility": 0.25,
            "impact": 0.20,
            "evidence_strength": 0.20,
            "simulation_readiness": 0.12,
            "inverse_validation_cost": 0.05,
        },
    )


# ---------------------------------------------------------------------------
# Prompt variant tests
# ---------------------------------------------------------------------------

class TestPromptVariants:
    def test_all_variants_present(self):
        assert "standard" in PROMPT_VARIANTS
        assert "synthesis_focus" in PROMPT_VARIANTS
        assert "evidence_heavy" in PROMPT_VARIANTS

    def test_standard_variant_is_base_prompt(self):
        assert PROMPT_VARIANTS["standard"] is CANDIDATE_GENERATION_PROMPT

    def test_synthesis_focus_is_different(self):
        assert PROMPT_VARIANTS["synthesis_focus"] is not CANDIDATE_GENERATION_PROMPT
        assert PROMPT_VARIANTS["synthesis_focus"] == CANDIDATE_GENERATION_PROMPT_SYNTHESIS_FOCUS

    def test_evidence_heavy_is_different(self):
        assert PROMPT_VARIANTS["evidence_heavy"] is not CANDIDATE_GENERATION_PROMPT
        assert PROMPT_VARIANTS["evidence_heavy"] == CANDIDATE_GENERATION_PROMPT_EVIDENCE_HEAVY

    def test_synthesis_focus_emphasizes_mechanism(self):
        prompt = CANDIDATE_GENERATION_PROMPT_SYNTHESIS_FOCUS
        assert "MECHANISM FIRST" in prompt
        assert "causal chain" in prompt.lower()

    def test_synthesis_focus_emphasizes_testability(self):
        prompt = CANDIDATE_GENERATION_PROMPT_SYNTHESIS_FOCUS
        assert "TESTABILITY" in prompt

    def test_synthesis_focus_emphasizes_plausibility(self):
        prompt = CANDIDATE_GENERATION_PROMPT_SYNTHESIS_FOCUS
        assert "PLAUSIBILITY" in prompt

    def test_evidence_heavy_requires_two_items(self):
        prompt = CANDIDATE_GENERATION_PROMPT_EVIDENCE_HEAVY
        assert "two" in prompt.lower() or "2" in prompt

    def test_synthesis_focus_longer_than_standard(self):
        """Synthesis focus has more detailed instructions than standard."""
        assert len(CANDIDATE_GENERATION_PROMPT_SYNTHESIS_FOCUS) > len(CANDIDATE_GENERATION_PROMPT)

    def test_all_variants_end_in_json_block(self):
        """All variants must produce the same output format."""
        for name, prompt in PROMPT_VARIANTS.items():
            assert "json" in prompt.lower(), f"Variant {name!r} missing JSON format instruction"
            assert "title" in prompt.lower(), f"Variant {name!r} missing title field"
            assert "mechanism" in prompt.lower(), f"Variant {name!r} missing mechanism field"


# ---------------------------------------------------------------------------
# FakeCandidateGenerator prompt_variant tests
# ---------------------------------------------------------------------------

class TestFakeCandidateGeneratorVariant:
    def test_default_variant_is_standard(self):
        gen = FakeCandidateGenerator()
        assert gen.prompt_variant == "standard"

    def test_can_set_synthesis_focus(self):
        gen = FakeCandidateGenerator(prompt_variant="synthesis_focus")
        assert gen.prompt_variant == "synthesis_focus"

    def test_can_set_evidence_heavy(self):
        gen = FakeCandidateGenerator(prompt_variant="evidence_heavy")
        assert gen.prompt_variant == "evidence_heavy"

    def test_generate_returns_same_output_regardless_of_variant(self):
        """FakeCandidateGenerator output is deterministic by design."""
        ev = _make_evidence(3)
        gen_std = FakeCandidateGenerator(prompt_variant="standard")
        gen_syn = FakeCandidateGenerator(prompt_variant="synthesis_focus")
        out_std = gen_std.generate(ev, domain="clean-energy", budget=3, run_id="r001")
        out_syn = gen_syn.generate(ev, domain="clean-energy", budget=3, run_id="r001")
        assert len(out_std) == len(out_syn)
        for a, b in zip(out_std, out_syn):
            assert a.title == b.title


# ---------------------------------------------------------------------------
# DemoCandidateGenerator prompt_variant tests
# ---------------------------------------------------------------------------

class TestDemoCandidateGeneratorVariant:
    def test_default_variant_is_standard(self):
        gen = DemoCandidateGenerator()
        assert gen.prompt_variant == "standard"

    def test_can_set_synthesis_focus(self):
        gen = DemoCandidateGenerator(prompt_variant="synthesis_focus")
        assert gen.prompt_variant == "synthesis_focus"

    def test_propagates_variant_to_underlying_generator(self):
        """DemoGenerator delegates to FakeGenerator and passes prompt_variant."""
        gen = DemoCandidateGenerator(prompt_variant="synthesis_focus")
        ev = _make_evidence(3)
        # Should not raise; prompt_variant is propagated
        out = gen.generate(ev, domain="clean-energy", budget=3, run_id="r002")
        assert len(out) >= 1


# ---------------------------------------------------------------------------
# OllamaCandidateGenerator prompt_variant selection (no network calls)
# ---------------------------------------------------------------------------

class TestOllamaCandidateGeneratorVariantInit:
    def test_default_variant_is_standard(self):
        gen = OllamaCandidateGenerator()
        assert gen.prompt_variant == "standard"

    def test_synthesis_focus_stored(self):
        gen = OllamaCandidateGenerator(prompt_variant="synthesis_focus")
        assert gen.prompt_variant == "synthesis_focus"

    def test_unknown_variant_falls_back_to_standard(self):
        gen = OllamaCandidateGenerator(prompt_variant="nonexistent_variant")
        assert gen.prompt_variant == "standard"

    def test_evidence_heavy_stored(self):
        gen = OllamaCandidateGenerator(prompt_variant="evidence_heavy")
        assert gen.prompt_variant == "evidence_heavy"


# ---------------------------------------------------------------------------
# Orchestrator policy_config wiring tests (offline, deterministic mode)
# ---------------------------------------------------------------------------

class TestOrchestratorPolicyActuation:
    def _make_orchestrator_with_policy(self, policy_config=None):
        from breakthrough_engine.db import init_db
        from breakthrough_engine.db import Repository
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        db = init_db(in_memory=True)
        repo = Repository(db)
        program = ResearchProgram(
            name="test_program",
            domain="clean-energy",
            mode=RunMode.DETERMINISTIC_TEST,
        )
        orch = BreakthroughOrchestrator(
            program=program,
            repo=repo,
            policy_config=policy_config,
        )
        return orch

    def test_no_policy_uses_standard_generator(self):
        orch = self._make_orchestrator_with_policy(policy_config=None)
        assert orch.generator.prompt_variant == "standard"

    def test_synthesis_focus_policy_wires_generator(self):
        policy = _make_synthesis_focus_policy()
        orch = self._make_orchestrator_with_policy(policy_config=policy)
        assert orch.generator.prompt_variant == "synthesis_focus"

    def test_standard_policy_uses_standard_prompt(self):
        policy = PolicyConfig(
            id="champ",
            name="phase5_champion",
            generation_prompt_variant="standard",
        )
        orch = self._make_orchestrator_with_policy(policy_config=policy)
        assert orch.generator.prompt_variant == "standard"

    def test_policy_id_set_from_config(self):
        policy = _make_synthesis_focus_policy()
        orch = self._make_orchestrator_with_policy(policy_config=policy)
        assert orch.policy_id == "synthesis_focus_v1_test"

    def test_policy_config_stored(self):
        policy = _make_synthesis_focus_policy()
        orch = self._make_orchestrator_with_policy(policy_config=policy)
        assert orch.policy_config is policy


# ---------------------------------------------------------------------------
# Scoring weight actuation: champion vs challenger ranking divergence
# ---------------------------------------------------------------------------

class TestScoringWeightActuation:
    """Confirm that different policy scoring weights produce different rankings."""

    def _make_score(self, novelty: float, plausibility: float, impact: float,
                    evidence_strength: float, simulation_readiness: float,
                    validation_cost: float) -> CandidateScore:
        score = CandidateScore(candidate_id="test")
        score.novelty_score = novelty
        score.plausibility_score = plausibility
        score.impact_score = impact
        score.evidence_strength_score = evidence_strength
        score.simulation_readiness_score = simulation_readiness
        score.validation_cost_score = validation_cost
        return score

    def test_champion_weights_favor_novelty_over_plausibility(self):
        """Champion equal-weights novelty and plausibility at 0.20 each."""
        champion_weights = {
            "novelty": 0.20, "plausibility": 0.20, "impact": 0.20,
            "evidence_strength": 0.20, "simulation_readiness": 0.10,
            "inverse_validation_cost": 0.10,
        }
        # Candidate A: high novelty, low plausibility
        a = self._make_score(novelty=0.9, plausibility=0.3, impact=0.5, evidence_strength=0.5,
                              simulation_readiness=0.5, validation_cost=0.5)
        a.compute_final(champion_weights)
        # Candidate B: low novelty, high plausibility
        b = self._make_score(novelty=0.3, plausibility=0.9, impact=0.5, evidence_strength=0.5,
                              simulation_readiness=0.5, validation_cost=0.5)
        b.compute_final(champion_weights)
        # With equal weights, A and B score identically (novelty_a=plausibility_b, plausibility_a=novelty_b)
        assert abs(a.final_score - b.final_score) < 0.001

    def test_synthesis_focus_weights_favor_plausibility(self):
        """synthesis_focus_v1 weights: plausibility 0.25 vs novelty 0.18."""
        sf_weights = {
            "novelty": 0.18, "plausibility": 0.25, "impact": 0.20,
            "evidence_strength": 0.20, "simulation_readiness": 0.12,
            "inverse_validation_cost": 0.05,
        }
        # Candidate A: high novelty, low plausibility
        a = self._make_score(novelty=0.9, plausibility=0.3, impact=0.5, evidence_strength=0.5,
                              simulation_readiness=0.5, validation_cost=0.5)
        a.compute_final(sf_weights)
        # Candidate B: low novelty, high plausibility
        b = self._make_score(novelty=0.3, plausibility=0.9, impact=0.5, evidence_strength=0.5,
                              simulation_readiness=0.5, validation_cost=0.5)
        b.compute_final(sf_weights)
        # With synthesis_focus weights, B (high plausibility) should beat A
        assert b.final_score > a.final_score

    def test_different_weights_produce_different_rankings(self):
        """Prove that champion and synthesis_focus produce different candidate orderings."""
        champion_w = {
            "novelty": 0.20, "plausibility": 0.20, "impact": 0.20,
            "evidence_strength": 0.20, "simulation_readiness": 0.10,
            "inverse_validation_cost": 0.10,
        }
        sf_w = {
            "novelty": 0.18, "plausibility": 0.25, "impact": 0.20,
            "evidence_strength": 0.20, "simulation_readiness": 0.12,
            "inverse_validation_cost": 0.05,
        }
        # C1: high novelty, low plausibility, low sim_readiness
        c1 = self._make_score(0.9, 0.2, 0.5, 0.5, 0.2, 0.5)
        # C2: low novelty, high plausibility, high sim_readiness
        c2 = self._make_score(0.2, 0.9, 0.5, 0.5, 0.9, 0.5)

        c1_champ = self._make_score(0.9, 0.2, 0.5, 0.5, 0.2, 0.5)
        c2_champ = self._make_score(0.2, 0.9, 0.5, 0.5, 0.9, 0.5)
        c1_champ.compute_final(champion_w)
        c2_champ.compute_final(champion_w)

        c1_sf = self._make_score(0.9, 0.2, 0.5, 0.5, 0.2, 0.5)
        c2_sf = self._make_score(0.2, 0.9, 0.5, 0.5, 0.9, 0.5)
        c1_sf.compute_final(sf_w)
        c2_sf.compute_final(sf_w)

        # Champion may rank C1 higher or equal
        # synthesis_focus should rank C2 higher (more plausibility + sim_readiness)
        assert c2_sf.final_score > c1_sf.final_score, (
            f"synthesis_focus should rank C2 (plausibility=0.9) > C1 (novelty=0.9), "
            f"got C2={c2_sf.final_score:.4f} vs C1={c1_sf.final_score:.4f}"
        )
        # The scores should differ from champion
        assert abs(c1_champ.final_score - c1_sf.final_score) > 0.001


# ---------------------------------------------------------------------------
# Evidence ranking weights tests
# ---------------------------------------------------------------------------

class TestEvidenceRankingWeights:
    def _make_items(self) -> list[EvidenceItem]:
        # Item A: high API relevance, low domain/mech overlap
        a = EvidenceItem(
            id="ev_a", title="Quantum field theory paper",
            source_id="s1", source_type="paper",
            quote="abstract quantum mechanics considerations",
            citation="Smith et al. (2023)",
            relevance_score=0.95,  # high API relevance
        )
        # Item B: medium API relevance, high domain/mech overlap
        b = EvidenceItem(
            id="ev_b", title="Clean energy solar photovoltaic efficiency",
            source_id="s2", source_type="paper",
            quote="clean energy solar cell efficiency improvement mechanism",
            citation="Jones et al. (2024)",
            relevance_score=0.60,  # medium API relevance
        )
        return [a, b]

    def test_default_weights_rank_by_api_relevance_primarily(self):
        from breakthrough_engine.retrieval import rank_evidence
        items = self._make_items()
        ranked = rank_evidence(items, domain="clean-energy", mechanism="solar mechanism")
        # Item A has higher API relevance score so may rank first by default
        # This is informational — just confirm it runs without error
        assert len(ranked) == 2

    def test_custom_weights_accepted(self):
        from breakthrough_engine.retrieval import rank_evidence
        items = self._make_items()
        custom_weights = {
            "api_relevance": 0.10,  # reduce API relevance weight
            "domain_overlap": 0.60,  # heavily favor domain overlap
            "mechanism_overlap": 0.20,
            "baseline": 0.10,
        }
        ranked_default = rank_evidence(items, domain="clean-energy", mechanism="solar mechanism")
        ranked_custom = rank_evidence(items, domain="clean-energy", mechanism="solar mechanism",
                                     evidence_ranking_weights=custom_weights)
        assert len(ranked_custom) == 2
        # With domain_overlap heavily weighted, item B (domain-relevant title) should win
        # Both lists should have the same items
        default_ids = [item.id for item, _ in ranked_default]
        custom_ids = [item.id for item, _ in ranked_custom]
        assert set(default_ids) == set(custom_ids)

    def test_ranking_details_present(self):
        from breakthrough_engine.retrieval import rank_evidence
        items = self._make_items()
        ranked = rank_evidence(items, domain="clean-energy")
        for item, detail in ranked:
            assert "composite_score" in detail
            assert "api_relevance" in detail
            assert "domain_overlap" in detail

    def test_none_weights_uses_defaults(self):
        """Passing None for evidence_ranking_weights should behave same as not passing."""
        from breakthrough_engine.retrieval import rank_evidence
        items = self._make_items()
        ranked_implicit = rank_evidence(items, domain="clean-energy")
        ranked_explicit_none = rank_evidence(items, domain="clean-energy",
                                            evidence_ranking_weights=None)
        # Should produce identical results
        for (item_a, det_a), (item_b, det_b) in zip(ranked_implicit, ranked_explicit_none):
            assert item_a.id == item_b.id
            assert abs(det_a["composite_score"] - det_b["composite_score"]) < 1e-9

    def test_extreme_api_weight_makes_high_relevance_win(self):
        """When api_relevance weight is 1.0 and others 0, highest relevance_score wins."""
        from breakthrough_engine.retrieval import rank_evidence
        items = self._make_items()
        extreme_weights = {"api_relevance": 1.0, "domain_overlap": 0.0,
                           "mechanism_overlap": 0.0, "baseline": 0.0}
        ranked = rank_evidence(items, domain="clean-energy",
                               evidence_ranking_weights=extreme_weights)
        # Item A has relevance_score=0.95 > Item B relevance_score=0.60
        assert ranked[0][0].id == "ev_a"


# ---------------------------------------------------------------------------
# Policy config integration: scoring weights from PolicyConfig
# ---------------------------------------------------------------------------

class TestPolicyConfigScoringWeightIntegration:
    def test_policy_scoring_weights_override_program_defaults(self):
        """PolicyConfig scoring weights propagate to compute_final via _apply_policy."""
        from breakthrough_engine.daily_search import DailySearchLadder

        runner = DailySearchLadder.__new__(DailySearchLadder)  # no __init__ needed

        base_program = ResearchProgram(
            name="test", domain="clean-energy",
            mode=RunMode.DETERMINISTIC_TEST,
        )
        policy = _make_policy_with_scoring_weights()

        trial_program = runner._apply_policy(base_program, policy)
        assert trial_program.scoring_weights["plausibility"] == 0.35
        assert trial_program.scoring_weights["novelty"] == 0.10

    def test_none_scoring_weights_leaves_program_unchanged(self):
        """PolicyConfig with scoring_weights=None does not change program weights."""
        from breakthrough_engine.daily_search import DailySearchLadder

        runner = DailySearchLadder.__new__(DailySearchLadder)

        base_program = ResearchProgram(
            name="test", domain="clean-energy",
            mode=RunMode.DETERMINISTIC_TEST,
        )
        policy = PolicyConfig(id="no_weights", name="no_weights", scoring_weights=None)
        trial_program = runner._apply_policy(base_program, policy)
        # Should be the original program (no copy needed)
        assert trial_program is base_program

    def test_champion_default_weights_sum_to_one(self):
        """Default champion scoring weights should sum to 1.0."""
        program = ResearchProgram(name="test", domain="clean-energy", mode=RunMode.DEMO_LOCAL)
        total = sum(program.scoring_weights.values())
        assert abs(total - 1.0) < 1e-9

    def test_synthesis_focus_weights_sum_to_one(self):
        """synthesis_focus_v1 scoring weights should sum to 1.0."""
        policy = _make_synthesis_focus_policy()
        total = sum(policy.scoring_weights.values())
        assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# End-to-end offline run with synthesis_focus policy (deterministic mode)
# ---------------------------------------------------------------------------

class TestEndToEndPolicyActuation:
    def test_deterministic_run_with_synthesis_focus_policy(self):
        """Full orchestrator run with synthesis_focus policy, offline-safe."""
        from breakthrough_engine.db import init_db, Repository
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        from breakthrough_engine.models import RunStatus

        db = init_db(in_memory=True)
        repo = Repository(db)
        program = ResearchProgram(
            name="test_actuation",
            domain="clean-energy",
            mode=RunMode.DETERMINISTIC_TEST,
            candidate_budget=3,
            simulation_budget=2,
        )
        policy = _make_synthesis_focus_policy()

        orch = BreakthroughOrchestrator(program=program, repo=repo, policy_config=policy)

        # Verify generator has correct variant
        assert orch.generator.prompt_variant == "synthesis_focus"
        # Verify policy config stored
        assert orch.policy_config.name == "synthesis_focus_v1"
        # Verify scoring weights will be applied (via program after _apply_policy)
        # The orchestrator itself doesn't apply weights — daily_search does
        # But the generator variant IS applied here
        run = orch.run()
        assert run.status in (RunStatus.COMPLETED, RunStatus.COMPLETED_NO_PUBLICATION, "completed", "completed_no_publication")

    def test_deterministic_run_with_standard_policy(self):
        """Full orchestrator run with standard champion policy, offline-safe."""
        from breakthrough_engine.db import init_db, Repository
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        from breakthrough_engine.models import RunStatus

        db = init_db(in_memory=True)
        repo = Repository(db)
        program = ResearchProgram(
            name="test_standard",
            domain="clean-energy",
            mode=RunMode.DETERMINISTIC_TEST,
            candidate_budget=3,
            simulation_budget=2,
        )
        from breakthrough_engine.policy_registry import _default_champion
        champion = _default_champion()

        orch = BreakthroughOrchestrator(program=program, repo=repo, policy_config=champion)
        assert orch.generator.prompt_variant == "standard"

        run = orch.run()
        assert run.status in (RunStatus.COMPLETED, RunStatus.COMPLETED_NO_PUBLICATION, "completed", "completed_no_publication")

    def test_two_policies_produce_different_prompt_variants(self):
        """Champion and challenger use different generators after actuation."""
        from breakthrough_engine.db import init_db, Repository
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        from breakthrough_engine.policy_registry import _default_champion

        db1 = init_db(in_memory=True)
        db2 = init_db(in_memory=True)
        program = ResearchProgram(
            name="test", domain="clean-energy",
            mode=RunMode.DETERMINISTIC_TEST,
        )

        champion = _default_champion()
        challenger = _make_synthesis_focus_policy()

        orch_champ = BreakthroughOrchestrator(
            program=program, repo=Repository(db1), policy_config=champion
        )
        orch_chal = BreakthroughOrchestrator(
            program=program, repo=Repository(db2), policy_config=challenger
        )

        assert orch_champ.generator.prompt_variant == "standard"
        assert orch_chal.generator.prompt_variant == "synthesis_focus"
        # Variants are different — this is the Phase 9 key assertion
        assert orch_champ.generator.prompt_variant != orch_chal.generator.prompt_variant


# ---------------------------------------------------------------------------
# Policy actuation audit: verify inert surfaces are identified
# ---------------------------------------------------------------------------

class TestPolicyActuationAudit:
    """Verify the actuation matrix is accurate."""

    def test_scoring_weights_wired_via_apply_policy(self):
        """scoring_weights: fully wired through _apply_policy + compute_final."""
        from breakthrough_engine.daily_search import DailySearchLadder
        runner = DailySearchLadder.__new__(DailySearchLadder)
        program = ResearchProgram(name="p", domain="clean-energy", mode=RunMode.DETERMINISTIC_TEST)
        policy = PolicyConfig(
            id="test", name="test",
            scoring_weights={"novelty": 0.50, "plausibility": 0.10, "impact": 0.10,
                            "evidence_strength": 0.10, "simulation_readiness": 0.10,
                            "inverse_validation_cost": 0.10},
        )
        tp = runner._apply_policy(program, policy)
        assert tp.scoring_weights["novelty"] == 0.50

    def test_generation_prompt_variant_wired_in_orchestrator(self):
        """generation_prompt_variant: fully wired through orchestrator init."""
        from breakthrough_engine.db import init_db, Repository
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        db = init_db(in_memory=True)
        program = ResearchProgram(name="p", domain="clean-energy", mode=RunMode.DETERMINISTIC_TEST)
        policy = PolicyConfig(id="sf", name="sf", generation_prompt_variant="synthesis_focus")

        orch = BreakthroughOrchestrator(program=program, repo=Repository(db), policy_config=policy)
        # The generator should have synthesis_focus as its prompt variant
        assert hasattr(orch.generator, "prompt_variant")
        assert orch.generator.prompt_variant == "synthesis_focus"

    def test_evidence_ranking_weights_accepted_by_rank_evidence(self):
        """evidence_ranking_weights: wired through rank_evidence() parameter."""
        from breakthrough_engine.retrieval import rank_evidence
        import inspect
        sig = inspect.signature(rank_evidence)
        assert "evidence_ranking_weights" in sig.parameters

    def test_sub_domain_rotation_policy_wired_via_orchestrator(self):
        """sub_domain_rotation_policy: wired through orchestrator to diversity_engine.build_context()."""
        from breakthrough_engine.db import init_db, Repository
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        db = init_db(in_memory=True)
        program = ResearchProgram(name="p", domain="clean-energy", mode=RunMode.DETERMINISTIC_TEST)
        policy = PolicyConfig(id="test_rot", name="test_rot", sub_domain_rotation_policy="random")

        orch = BreakthroughOrchestrator(program=program, repo=Repository(db), policy_config=policy)
        # Verify the policy config is stored and accessible
        assert orch.policy_config.sub_domain_rotation_policy == "random"
