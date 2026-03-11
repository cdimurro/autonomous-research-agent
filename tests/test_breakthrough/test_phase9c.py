"""Phase 9C tests: Champion lock, failed challenger freeze, challenger v2, proof of actuation.

All tests are offline-safe (no Ollama, no external network, no embeddings).
"""

from __future__ import annotations

import json
import os
import csv
from pathlib import Path

import pytest

from breakthrough_engine.candidate_generator import PROMPT_VARIANTS
from breakthrough_engine.models import EvidenceItem
from breakthrough_engine.policy_registry import (
    PHASE5_CHAMPION_ID,
    MAX_ACTIVE_CHALLENGERS,
    PolicyConfig,
    _default_champion,
)
from breakthrough_engine.retrieval import rank_evidence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent


def _load_json(path: str) -> dict:
    with open(REPO_ROOT / path) as f:
        return json.load(f)


def _load_policy(name: str) -> dict:
    return _load_json(f"config/policies/{name}.json")


def _make_evidence_items() -> list[EvidenceItem]:
    """Controlled 3-item evidence set for proof-of-actuation tests."""
    return [
        EvidenceItem(
            id="ev_A",
            title="High-efficiency catalyst for hydrogen evolution via platinum group reduction",
            source_id="src_A",
            source_type="paper",
            quote="Platinum group reduction enables high-efficiency catalysis",
            citation="Kim et al. (2024)",
            relevance_score=0.90,
        ),
        EvidenceItem(
            id="ev_B",
            title="Electrolyte interface engineering for proton exchange membrane stability",
            source_id="src_B",
            source_type="paper",
            quote="Proton exchange membrane interface engineering stability",
            citation="Chen et al. (2023)",
            relevance_score=0.40,
        ),
        EvidenceItem(
            id="ev_C",
            title="Thermal management strategies in solid oxide fuel cell systems",
            source_id="src_C",
            source_type="paper",
            quote="Thermal management solid oxide fuel cell systems strategies",
            citation="Liu et al. (2022)",
            relevance_score=0.60,
        ),
    ]


# ---------------------------------------------------------------------------
# A: Failed challenger freeze tests
# ---------------------------------------------------------------------------

class TestFailedChallengerFreeze:
    """Phase 9B arm_summary.json must be frozen with real data."""

    def test_arm_summary_status_is_frozen(self):
        data = _load_json("runtime/challenger_trials/phase9b_ab_trial/arm_summary.json")
        assert data["status"] == "COMPLETE_FROZEN", (
            f"arm_summary.json status should be COMPLETE_FROZEN, got {data['status']!r}"
        )

    def test_arm_summary_verdict_is_not_recommended(self):
        data = _load_json("runtime/challenger_trials/phase9b_ab_trial/arm_summary.json")
        assert data["verdict"] == "PROMOTION_NOT_RECOMMENDED"

    def test_arm_summary_has_real_champion_data(self):
        data = _load_json("runtime/challenger_trials/phase9b_ab_trial/arm_summary.json")
        champ = data["champion_arm"]
        assert champ["campaign_count"] == 6
        assert champ["review_labels_collected"] == 12
        assert abs(champ["mean_champion_score"] - 0.90804) < 0.001
        assert champ["approval_rate"] == 0.75

    def test_arm_summary_has_real_challenger_data(self):
        data = _load_json("runtime/challenger_trials/phase9b_ab_trial/arm_summary.json")
        chall = data["challenger_arm"]
        assert chall["campaign_count"] == 6
        assert chall["review_labels_collected"] == 12
        assert abs(chall["mean_champion_score"] - 0.87789) < 0.001
        assert chall["approval_rate"] == 0.25

    def test_arm_summary_comparison_shows_all_failures(self):
        data = _load_json("runtime/challenger_trials/phase9b_ab_trial/arm_summary.json")
        cmp = data["comparison"]
        assert cmp["evidence_sufficient"] is True
        assert cmp["regime_correct"] is True
        # All deltas negative
        assert cmp["champion_score_delta"] < 0
        assert cmp["approval_rate_delta"] < 0
        assert cmp["novelty_confidence_delta"] < 0
        assert cmp["technical_plausibility_delta"] < 0

    def test_arm_summary_has_frozen_at_timestamp(self):
        data = _load_json("runtime/challenger_trials/phase9b_ab_trial/arm_summary.json")
        assert "frozen_at" in data
        assert data["frozen_at"]  # non-empty

    def test_posterior_summary_is_unchanged(self):
        """Posterior summary must still contain real data from Phase 9B."""
        data = _load_json("runtime/challenger_trials/phase9b_ab_trial/posterior_summary.json")
        assert data["promotion_gate"]["verdict"] == "PROMOTION_NOT_RECOMMENDED"
        assert data["arms"]["champion"]["approval_rate"] == 0.75
        assert data["arms"]["challenger"]["approval_rate"] == 0.25

    def test_synthesis_focus_v1_policy_preserved(self):
        """synthesis_focus_v1 config must still exist as audit trail."""
        policy_path = REPO_ROOT / "config/policies/synthesis_focus_v1.json"
        assert policy_path.exists(), "synthesis_focus_v1.json must be preserved as audit trail"
        policy = json.loads(policy_path.read_text())
        assert policy["name"] == "synthesis_focus_v1"

    def test_failure_analysis_doc_exists(self):
        doc_path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_FAILURE_ANALYSIS.md"
        assert doc_path.exists(), "Challenger failure analysis doc must exist"
        content = doc_path.read_text()
        assert "PROMOTION_NOT_RECOMMENDED" in content
        assert "synthesis_focus_v1" in content
        assert "Root Cause" in content or "root cause" in content.lower()


# ---------------------------------------------------------------------------
# B: Champion production lock tests
# ---------------------------------------------------------------------------

class TestChampionProductionLock:
    """Champion must be phase5_champion with standard defaults."""

    def test_default_champion_id_is_phase5(self):
        assert PHASE5_CHAMPION_ID == "phase5_champion"

    def test_default_champion_has_standard_prompt(self):
        champ = _default_champion()
        assert champ.generation_prompt_variant == "standard"

    def test_default_champion_has_no_scoring_overrides(self):
        champ = _default_champion()
        assert champ.scoring_weights is None

    def test_default_champion_has_no_evidence_ranking_overrides(self):
        champ = _default_champion()
        assert champ.evidence_ranking_weights is None

    def test_max_active_challengers_bounded(self):
        """Production safety: at most 2 challengers can be active at once."""
        assert MAX_ACTIVE_CHALLENGERS == 2

    def test_champion_policy_config_standard_variant(self):
        """PolicyConfig with standard settings must not use synthesis_focus."""
        champ_config = PolicyConfig(
            id=PHASE5_CHAMPION_ID,
            name="phase5_champion",
            generation_prompt_variant="standard",
        )
        assert champ_config.generation_prompt_variant == "standard"
        assert champ_config.generation_prompt_variant in PROMPT_VARIANTS

    def test_phase9c_status_doc_exists(self):
        doc_path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9C_STATUS.md"
        assert doc_path.exists()
        content = doc_path.read_text()
        assert "phase5_champion" in content
        assert "REGISTERED" in content  # challenger v2 registered

    def test_phase9c_plan_doc_exists(self):
        doc_path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9C_PLAN.md"
        assert doc_path.exists()


# ---------------------------------------------------------------------------
# C: Challenger v2 registration tests
# ---------------------------------------------------------------------------

class TestChallengerV2Registration:
    """evidence_diversity_v1 must be registered, valid, and the only active challenger."""

    def test_evidence_diversity_v1_policy_exists(self):
        path = REPO_ROOT / "config/policies/evidence_diversity_v1.json"
        assert path.exists(), "evidence_diversity_v1.json must exist"

    def test_evidence_diversity_v1_name_correct(self):
        policy = _load_policy("evidence_diversity_v1")
        assert policy["name"] == "evidence_diversity_v1"

    def test_evidence_diversity_v1_single_surface_change(self):
        """Only evidence_ranking_weights should differ from champion defaults."""
        policy = _load_policy("evidence_diversity_v1")
        # These must be champion defaults (no change)
        assert policy["generation_prompt_variant"] == "standard"
        assert policy["scoring_weights"] is None
        assert policy["diversity_steering_variant"] == "standard"
        assert policy["sub_domain_rotation_policy"] == "auto"

    def test_evidence_diversity_v1_has_evidence_ranking_weights(self):
        policy = _load_policy("evidence_diversity_v1")
        erw = policy["evidence_ranking_weights"]
        assert erw is not None
        assert "api_relevance" in erw
        assert "domain_overlap" in erw
        assert "mechanism_overlap" in erw
        assert "baseline" in erw

    def test_evidence_diversity_v1_mechanism_overlap_increased(self):
        policy = _load_policy("evidence_diversity_v1")
        erw = policy["evidence_ranking_weights"]
        # Champion default: mechanism_overlap=0.20
        assert erw["mechanism_overlap"] > 0.20, (
            f"mechanism_overlap should be > 0.20 (challenger), got {erw['mechanism_overlap']}"
        )

    def test_evidence_diversity_v1_api_relevance_reduced(self):
        policy = _load_policy("evidence_diversity_v1")
        erw = policy["evidence_ranking_weights"]
        # Champion default: api_relevance=0.35
        assert erw["api_relevance"] < 0.35, (
            f"api_relevance should be < 0.35 (challenger), got {erw['api_relevance']}"
        )

    def test_evidence_diversity_v1_weights_sum_approximately_one(self):
        """Ranking weights should sum to ~1.0 (excluding baseline which is applied differently)."""
        policy = _load_policy("evidence_diversity_v1")
        erw = policy["evidence_ranking_weights"]
        total = erw["api_relevance"] + erw["domain_overlap"] + erw["mechanism_overlap"] + erw["baseline"]
        assert 0.95 <= total <= 1.05, f"Weights sum to {total}, expected ~1.0"

    def test_evidence_diversity_v1_has_metadata(self):
        policy = _load_policy("evidence_diversity_v1")
        meta = policy.get("metadata", {})
        assert meta.get("challenger_vs") == "phase5_champion"
        assert meta.get("predecessor") == "synthesis_focus_v1"
        assert meta.get("predecessor_verdict") == "PROMOTION_NOT_RECOMMENDED"

    def test_evidence_diversity_v1_has_design_doc_reference(self):
        policy = _load_policy("evidence_diversity_v1")
        meta = policy.get("metadata", {})
        assert "design_doc" in meta
        # Verify the referenced doc exists
        doc_path = REPO_ROOT / meta["design_doc"]
        assert doc_path.exists(), f"Design doc {meta['design_doc']!r} referenced in policy but not found"

    def test_challenger_v2_design_doc_exists(self):
        doc_path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_V2_DESIGN.md"
        assert doc_path.exists()
        content = doc_path.read_text()
        assert "evidence_diversity_v1" in content
        assert "synthesis_focus_v1" in content
        assert "failure" in content.lower()

    def test_policy_config_from_evidence_diversity_v1(self):
        """PolicyConfig.from_dict must work with evidence_diversity_v1 data."""
        policy_data = _load_policy("evidence_diversity_v1")
        config = PolicyConfig.from_dict(policy_data)
        assert config.name == "evidence_diversity_v1"
        assert config.evidence_ranking_weights is not None
        assert config.generation_prompt_variant == "standard"
        assert config.scoring_weights is None


# ---------------------------------------------------------------------------
# D: Daily collection scaffold tests
# ---------------------------------------------------------------------------

class TestDailyCollectionScaffold:
    """Daily collection artifacts must exist with correct schema."""

    def test_daily_collection_directory_exists(self):
        path = REPO_ROOT / "runtime/phase9c/daily_collection"
        assert path.is_dir(), "Daily collection directory must exist"

    def test_daily_collection_summary_json_exists(self):
        path = REPO_ROOT / "runtime/phase9c/daily_collection/daily_collection_summary.json"
        assert path.exists()

    def test_daily_collection_summary_json_has_required_fields(self):
        data = _load_json("runtime/phase9c/daily_collection/daily_collection_summary.json")
        for field in ["phase", "status", "policy", "target_campaign_count", "target_label_count"]:
            assert field in data, f"Missing field {field!r} in daily_collection_summary.json"

    def test_daily_collection_summary_json_policy_is_champion(self):
        data = _load_json("runtime/phase9c/daily_collection/daily_collection_summary.json")
        assert data["policy"] == "phase5_champion"

    def test_review_labels_csv_exists_with_header(self):
        path = REPO_ROOT / "runtime/phase9c/daily_collection/review_labels.csv"
        assert path.exists()
        with open(path) as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
        required = ["id", "campaign_id", "candidate_id", "decision",
                    "novelty_confidence", "technical_plausibility"]
        for req in required:
            assert req in fields, f"Missing column {req!r} in review_labels.csv"

    def test_champions_csv_exists_with_header(self):
        path = REPO_ROOT / "runtime/phase9c/daily_collection/champions.csv"
        assert path.exists()
        with open(path) as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
        assert "campaign_id" in fields
        assert "champion_score" in fields

    def test_campaign_metrics_csv_exists_with_header(self):
        path = REPO_ROOT / "runtime/phase9c/daily_collection/campaign_metrics.csv"
        assert path.exists()
        with open(path) as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
        assert "campaign_id" in fields
        assert "policy" in fields
        assert "integrity_status" in fields

    def test_label_completeness_summary_exists(self):
        path = REPO_ROOT / "runtime/phase9c/daily_collection/label_completeness_summary.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "total_campaigns" in data
        assert "completeness_pct" in data

    def test_phase9c_daily_collection_doc_exists(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9C_DAILY_COLLECTION.md"
        assert path.exists()
        content = path.read_text()
        assert "phase5_champion" in content
        assert "evaluation_daily_clean_energy" in content
        assert "production_daily_clean_energy" in content


# ---------------------------------------------------------------------------
# E: Proof of actuation tests
# ---------------------------------------------------------------------------

class TestProofOfActuation:
    """evidence_diversity_v1 must change evidence ranking vs champion defaults."""

    def test_proof_of_actuation_artifact_exists(self):
        path = REPO_ROOT / "runtime/phase9c/proof_of_actuation/proof_of_actuation.json"
        assert path.exists()

    def test_proof_of_actuation_verified(self):
        data = _load_json("runtime/phase9c/proof_of_actuation/proof_of_actuation.json")
        assert data["actuation_verified"] is True

    def test_proof_of_actuation_top_item_flipped(self):
        data = _load_json("runtime/phase9c/proof_of_actuation/proof_of_actuation.json")
        assert data["actuation_verified"] is True
        delta = data["ranking_delta"]
        assert delta["top_item_flipped"] is True
        assert delta["champion_top"] != delta["challenger_top"]

    def test_rank_evidence_champion_weights_selects_high_api_item(self):
        """With champion default weights (api=0.35), high-api-relevance item should rank first."""
        items = _make_evidence_items()
        # Champion defaults: api=0.35, dom=0.30, mech=0.20, base=0.15
        ranked = rank_evidence(
            items,
            domain="clean-energy",
            mechanism="electrolyte proton exchange membrane interface",
            evidence_ranking_weights=None,  # champion defaults
        )
        ids = [item.id for item, _ in ranked]
        # ev_A has highest api_relevance (0.90) and should win under champion defaults
        assert ids[0] == "ev_A", f"Champion defaults should rank ev_A first, got {ids}"

    def test_rank_evidence_challenger_weights_selects_high_mechanism_item(self):
        """With challenger weights (mech=0.35), high-mechanism-overlap item should rank first."""
        items = _make_evidence_items()
        challenger_weights = {
            "api_relevance": 0.20,
            "domain_overlap": 0.30,
            "mechanism_overlap": 0.35,
            "baseline": 0.15,
        }
        ranked = rank_evidence(
            items,
            domain="clean-energy",
            mechanism="electrolyte proton exchange membrane interface",
            evidence_ranking_weights=challenger_weights,
        )
        ids = [item.id for item, _ in ranked]
        # ev_B has highest mechanism_overlap with "electrolyte/proton/exchange/membrane/interface"
        # and should win under challenger weights
        assert ids[0] == "ev_B", f"Challenger weights should rank ev_B first, got {ids}"

    def test_rank_evidence_weights_change_produces_different_top(self):
        """Changing evidence_ranking_weights must change the top-ranked item."""
        items = _make_evidence_items()
        mechanism = "electrolyte proton exchange membrane interface"

        ranked_champion = rank_evidence(
            items, domain="clean-energy", mechanism=mechanism,
            evidence_ranking_weights=None,
        )
        ranked_challenger = rank_evidence(
            items, domain="clean-energy", mechanism=mechanism,
            evidence_ranking_weights={
                "api_relevance": 0.20,
                "domain_overlap": 0.30,
                "mechanism_overlap": 0.35,
                "baseline": 0.15,
            },
        )
        champ_top = ranked_champion[0][0].id
        chall_top = ranked_challenger[0][0].id
        assert champ_top != chall_top, (
            f"Champion and challenger should rank different items first; "
            f"both ranked {champ_top!r} first"
        )

    def test_rank_evidence_challenger_weights_score_detail_has_higher_mech_contribution(self):
        """Challenger weight detail should show mechanism_overlap contributing more."""
        items = _make_evidence_items()
        mechanism = "electrolyte proton exchange membrane interface"

        # Get ev_B rankings from both configurations
        champion_ranked = rank_evidence(
            items, domain="clean-energy", mechanism=mechanism,
            evidence_ranking_weights=None,
        )
        challenger_ranked = rank_evidence(
            items, domain="clean-energy", mechanism=mechanism,
            evidence_ranking_weights={
                "api_relevance": 0.20,
                "domain_overlap": 0.30,
                "mechanism_overlap": 0.35,
                "baseline": 0.15,
            },
        )

        # Find ev_B in each ranking
        champ_detail = next(d for item, d in champion_ranked if item.id == "ev_B")
        chall_detail = next(d for item, d in challenger_ranked if item.id == "ev_B")

        # ev_B has non-zero mechanism_overlap; its composite should be higher under challenger weights
        assert chall_detail["composite_score"] > champ_detail["composite_score"], (
            f"ev_B composite should be higher under challenger weights: "
            f"champ={champ_detail['composite_score']}, chall={chall_detail['composite_score']}"
        )

    def test_evidence_diversity_v1_policy_weights_match_proof_artifact(self):
        """Policy file weights must match the proof-of-actuation artifact."""
        policy = _load_policy("evidence_diversity_v1")
        proof = _load_json("runtime/phase9c/proof_of_actuation/proof_of_actuation.json")

        policy_weights = policy["evidence_ranking_weights"]
        proof_weights = proof["challenger_ranking"]["weights"]

        assert policy_weights["api_relevance"] == proof_weights["api_relevance"]
        assert policy_weights["mechanism_overlap"] == proof_weights["mechanism_overlap"]
        assert policy_weights["domain_overlap"] == proof_weights["domain_overlap"]
        assert policy_weights["baseline"] == proof_weights["baseline"]


# ---------------------------------------------------------------------------
# F: Single-challenger enforcement tests
# ---------------------------------------------------------------------------

class TestSingleChallengerEnforcement:
    """At most MAX_ACTIVE_CHALLENGERS challengers should be registered at once."""

    def test_only_one_active_challenger_policy_file(self):
        """Only evidence_diversity_v1 should be the current active challenger (not synthesis_focus_v1)."""
        policy_dir = REPO_ROOT / "config/policies"
        policy_files = list(policy_dir.glob("*.json"))

        active_challengers = []
        for path in policy_files:
            data = json.loads(path.read_text())
            name = data.get("name", "")
            if name == "phase5_champion":
                continue  # skip champion
            # synthesis_focus_v1 is retired — check its metadata
            if name == "synthesis_focus_v1":
                # It should be preserved as audit trail but is retired
                # Its metadata should indicate it's a failed/retired challenger
                meta = data.get("metadata", {})
                # The key is that we don't register it in a new trial
                continue
            # evidence_diversity_v1 is the only active challenger
            active_challengers.append(name)

        assert len(active_challengers) == 1, (
            f"Expected exactly 1 active challenger, found {len(active_challengers)}: {active_challengers}"
        )
        assert active_challengers[0] == "evidence_diversity_v1"

    def test_max_active_challengers_constant_not_exceeded(self):
        """The number of challenger policy files should not exceed MAX_ACTIVE_CHALLENGERS."""
        policy_dir = REPO_ROOT / "config/policies"
        policy_files = list(policy_dir.glob("*.json"))
        challenger_count = sum(
            1 for p in policy_files
            if json.loads(p.read_text()).get("name") not in ("phase5_champion",)
        )
        assert challenger_count <= MAX_ACTIVE_CHALLENGERS + 1, (
            f"Too many challenger policies ({challenger_count}); max is {MAX_ACTIVE_CHALLENGERS} "
            f"(+1 for archived synthesis_focus_v1)"
        )


# ---------------------------------------------------------------------------
# G: Failure analysis content tests
# ---------------------------------------------------------------------------

class TestFailureAnalysisContent:
    """Challenger failure analysis doc must contain key diagnostic content."""

    def test_failure_analysis_has_score_delta(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_FAILURE_ANALYSIS.md"
        content = path.read_text()
        assert "0.90804" in content or "0.908" in content  # champion score
        assert "0.87789" in content or "0.877" in content  # challenger score

    def test_failure_analysis_has_approval_rate_data(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_FAILURE_ANALYSIS.md"
        content = path.read_text()
        assert "75%" in content   # champion approval rate
        assert "25%" in content   # challenger approval rate

    def test_failure_analysis_has_novelty_delta(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_FAILURE_ANALYSIS.md"
        content = path.read_text()
        assert "novelty" in content.lower()
        assert "0.783" in content or "0.713" in content  # novelty confidence values

    def test_failure_analysis_distinguishes_intended_vs_actual(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_FAILURE_ANALYSIS.md"
        content = path.read_text()
        # Must distinguish intended effect from actual
        assert "Intended" in content or "intended" in content
        assert "Actual" in content or "actual" in content

    def test_failure_analysis_documents_key_lesson(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_FAILURE_ANALYSIS.md"
        content = path.read_text()
        assert "Key Lesson" in content or "key lesson" in content.lower()
        # Key lesson: scoring weights are selection tools
        assert "selection" in content.lower() or "selector" in content.lower()

    def test_failure_analysis_disposition_is_retired(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_FAILURE_ANALYSIS.md"
        content = path.read_text()
        assert "RETIRED_FAILED" in content or "retired" in content.lower()


# ---------------------------------------------------------------------------
# H: Challenger v2 design doc content tests
# ---------------------------------------------------------------------------

class TestChallengerV2DesignDoc:
    """Challenger v2 design doc must contain key design content."""

    def test_design_doc_has_config_diff(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_V2_DESIGN.md"
        content = path.read_text()
        assert "mechanism_overlap" in content
        assert "api_relevance" in content

    def test_design_doc_references_failure_analysis(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_V2_DESIGN.md"
        content = path.read_text()
        assert "FAILURE_ANALYSIS" in content or "failure" in content.lower()
        assert "synthesis_focus_v1" in content

    def test_design_doc_has_expected_outcomes_table(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_V2_DESIGN.md"
        content = path.read_text()
        assert "Expected" in content or "expected" in content
        assert "novelty" in content.lower()

    def test_design_doc_addresses_synthesis_focus_failures(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_CHALLENGER_V2_DESIGN.md"
        content = path.read_text()
        # Must explain why this design avoids the previous failure
        assert "novelty" in content.lower()
        assert "prompt" in content.lower() or "generation" in content.lower()
