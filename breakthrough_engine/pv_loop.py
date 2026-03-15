"""PV optimization loop — end-to-end candidate generation, experiment,
scoring, and promotion for PV I-V characterization.

This is the first narrow-domain optimization loop. It:
1. Generates PV candidate parameter variations with realistic priors
2. Runs fixed experiments (STC, sweeps) via pvlib
3. Scores candidates against a baseline with robustness stress tests
4. Applies hard-fail gates and generates caveats
5. Promotes or rejects with conservative, selective policy
6. Persists idea memory and experiment memory
7. Uses memory to guide future proposals
"""

from __future__ import annotations

import logging
import math
import random
from typing import Optional

from .db import Repository, init_db
from .domain_models import (
    CandidateSpec,
    CandidateStatus,
    EvaluationResult,
    ExperimentMemoryEntry,
    IdeaMemoryEntry,
    PromotionDecision,
    PromotionRecord,
)
from .pv_domain import (
    DEFAULT_CELL_PARAMS,
    EXPERIMENT_TEMPLATES,
    check_metrics_plausibility,
    check_physical_plausibility,
    run_experiment,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Candidate generation — realistic priors (CC-BE-2406)
# ---------------------------------------------------------------------------

# Tighter parameter bounds grounded in commercial crystalline-Si module data.
# Sources: CEC module database typical ranges for mono/poly-Si modules.
#   I_L_ref:  7–13 A  (typical 60-cell modules: 8–10 A)
#   I_o_ref:  1e-12–1e-9 A  (good junction: ~1e-11; poor: ~1e-9)
#   R_s:      0.1–1.5 ohm   (typical 0.3–0.6; below 0.1 is unrealistic)
#   R_sh_ref: 100–1500 ohm  (typical 300–600; above 1500 is aspirational)
#   a_ref:    1.0–2.2 V     (ideality factor 1.0–1.5 typical for Si)
#   alpha_sc: 0.001–0.006 A/C (typical ~0.003 for c-Si)
PARAM_RANGES = {
    "I_L_ref": (7.0, 13.0),       # A — photocurrent (tighter: commercial c-Si)
    "I_o_ref": (1e-12, 1e-9),     # A — saturation current (realistic junction range)
    "R_s": (0.1, 1.5),            # ohm — series resistance (practical range)
    "R_sh_ref": (100.0, 1500.0),  # ohm — shunt resistance (commercial modules)
    "a_ref": (1.0, 2.2),          # V — ideality factor (physical for Si)
    "alpha_sc": (0.001, 0.006),   # A/C — temp coeff of Isc (c-Si range)
}

# Candidate families with physically-grounded perturbation bounds.
#
# Each family targets a specific physical improvement mechanism:
#   - reduced_series_resistance: metallization/contact improvements (Rs)
#   - improved_junction_quality: passivation/recombination reduction (I_o)
#   - enhanced_photocurrent: anti-reflection/texturing gains (I_L)
#   - improved_shunt_resistance: fewer micro-shunts/defects (R_sh)
#   - combined_moderate: realistic multi-parameter co-optimization
#   - bounded_aggressive: near-limit parameters with physical justification
#
# Perturbation ranges are bounded to plausible improvement magnitudes:
#   - Rs reductions: 0.05–0.25 ohm (not >50% of typical value)
#   - I_o multipliers: 0.1–0.7 (modest junction improvement, not orders of magnitude)
#   - I_L deltas: 0.2–1.0 A (incremental absorption gains)
#   - R_sh deltas: 50–300 ohm (realistic defect reduction)
CANDIDATE_FAMILIES = [
    {
        "family": "reduced_series_resistance",
        "rationale": "Lower Rs via improved metallization/contacts reduces ohmic losses, "
                     "improving fill factor and Pmax (typical improvement: 0.05–0.2 ohm)",
        "perturbations": {"R_s": (-0.25, -0.05)},
    },
    {
        "family": "improved_junction_quality",
        "rationale": "Lower I_o via better passivation reduces recombination current, "
                     "improving Voc (realistic: 30–90% reduction in I_o)",
        "perturbations": {"I_o_ref": (0.1, 0.7)},  # multiplier: 0.1x–0.7x
    },
    {
        "family": "enhanced_photocurrent",
        "rationale": "Higher I_L via anti-reflection coating or texturing improves "
                     "light absorption (typical gain: 0.2–1.0 A)",
        "perturbations": {"I_L_ref": (0.2, 1.0)},
    },
    {
        "family": "improved_shunt_resistance",
        "rationale": "Higher Rsh via reduced micro-shunts decreases leakage current, "
                     "improving Voc and FF (typical gain: 50–250 ohm)",
        "perturbations": {"R_sh_ref": (50.0, 250.0)},
    },
    {
        "family": "combined_moderate",
        "rationale": "Co-optimized Rs reduction and Rsh improvement reflecting "
                     "realistic multi-step process improvement",
        "perturbations": {"R_s": (-0.15, -0.03), "R_sh_ref": (30.0, 150.0)},
    },
    {
        "family": "bounded_aggressive",
        "rationale": "Near-limit optimization across Rs, I_o, and Rsh — physically "
                     "possible but represents best-in-class manufacturing",
        "perturbations": {"R_s": (-0.20, -0.10), "I_o_ref": (0.15, 0.5), "R_sh_ref": (100.0, 300.0)},
    },
]


def _check_cross_parameter_plausibility(params: dict) -> tuple[bool, list[str]]:
    """Reject unrealistic parameter *combinations* at generation time.

    This catches combinations that are individually within bounds but
    physically inconsistent together.
    """
    reasons: list[str] = []

    # Very low Rs with very low Rsh is contradictory: good contacts but
    # severe shunting indicates fabrication incompatibility
    rs = params.get("R_s", 0.5)
    rsh = params.get("R_sh_ref", 400.0)
    if rs < 0.15 and rsh < 150:
        reasons.append(
            f"Contradictory: low Rs ({rs:.3f}) with low Rsh ({rsh:.0f}) — "
            "good contacts with severe shunting is physically inconsistent"
        )

    # Very high photocurrent with very high saturation current is
    # contradictory: excellent absorption but poor junction quality
    il = params.get("I_L_ref", 9.5)
    io = params.get("I_o_ref", 1e-10)
    if il > 11.0 and io > 5e-9:
        reasons.append(
            f"Contradictory: high I_L ({il:.1f}A) with high I_o ({io:.2e}A) — "
            "excellent absorption but poor junction is unrealistic"
        )

    # Ideality factor > 2.0 with very low I_o is inconsistent:
    # high ideality implies recombination-dominated, contradicting low I_o
    a_ref = params.get("a_ref", 1.5)
    if a_ref > 2.0 and io < 1e-11:
        reasons.append(
            f"Contradictory: high ideality ({a_ref:.2f}) with very low I_o ({io:.2e}) — "
            "high recombination ideality contradicts excellent junction"
        )

    return len(reasons) == 0, reasons


# Proposal rationale tags (CC-BE-2409)
PROPOSAL_TAG_MEMORY = "memory-supported"
PROPOSAL_TAG_EXPLORATORY = "exploratory"
PROPOSAL_TAG_RECOVERY = "recovery"
PROPOSAL_TAG_RETRY = "retry-with-correction"


def _compute_family_weights(
    prior_lessons: Optional[list[dict]],
    experiment_memories: Optional[list[dict]] = None,
) -> tuple[dict[str, float], dict[str, str]]:
    """Compute per-family selection weights from memory.

    Returns (weights_dict, rationale_tags_dict).
    Families with promoted history get higher weight.
    Families with consistent hard-fails get down-ranked.
    Families whose sweeps exposed fragility get recovery tags.
    """
    weights: dict[str, float] = {f["family"]: 1.0 for f in CANDIDATE_FAMILIES}
    tags: dict[str, str] = {f["family"]: PROPOSAL_TAG_EXPLORATORY for f in CANDIDATE_FAMILIES}

    if not prior_lessons:
        return weights, tags

    family_stats: dict[str, dict] = {}
    for lesson in prior_lessons:
        fam = lesson.get("candidate_family", "")
        outcome = lesson.get("outcome", "")
        if not fam:
            continue
        stats = family_stats.setdefault(fam, {"promoted": 0, "rejected": 0, "hard_fail": 0, "total": 0})
        stats["total"] += 1
        if outcome == "promoted":
            stats["promoted"] += 1
        elif outcome == "hard_fail":
            stats["hard_fail"] += 1
        elif outcome == "rejected":
            stats["rejected"] += 1

    # Fragile families from experiment memory
    fragile_families: set[str] = set()
    if experiment_memories:
        for mem in experiment_memories:
            weakness = mem.get("weakness_exposed", "")
            if weakness and ("sensitivity" in weakness.lower() or "variation" in weakness.lower()):
                # Try to associate with a family via candidate_id matching
                fragile_families.add(mem.get("candidate_id", ""))

    for fam, stats in family_stats.items():
        if fam not in weights:
            continue
        total = stats["total"]
        if total == 0:
            continue

        promote_rate = stats["promoted"] / total
        hard_fail_rate = stats["hard_fail"] / total

        if hard_fail_rate == 1.0:
            # All attempts hard-failed: heavily down-rank but don't exclude
            weights[fam] = 0.1
            tags[fam] = PROPOSAL_TAG_RETRY
            logger.info("Down-ranking family %s: 100%% hard-fail rate", fam)
        elif hard_fail_rate > 0.5:
            weights[fam] = 0.3
            tags[fam] = PROPOSAL_TAG_RETRY
        elif promote_rate > 0:
            # Has at least one promotion: memory-supported
            weights[fam] = 1.0 + promote_rate  # up to 2.0
            tags[fam] = PROPOSAL_TAG_MEMORY
        elif stats["rejected"] == total:
            # All rejected (not hard-fail): try with correction
            weights[fam] = 0.5
            tags[fam] = PROPOSAL_TAG_RECOVERY

    return weights, tags


def _select_families_weighted(
    families: list[dict],
    weights: dict[str, float],
    n: int,
    rng: random.Random,
) -> list[dict]:
    """Select n families using weighted sampling without replacement (then cycle)."""
    available = list(families)
    w = [weights.get(f["family"], 1.0) for f in available]
    total_w = sum(w)
    if total_w <= 0:
        return [available[i % len(available)] for i in range(n)]

    selected = []
    for _ in range(n):
        r = rng.random() * total_w
        cumulative = 0.0
        for idx, fw in enumerate(w):
            cumulative += fw
            if r <= cumulative:
                selected.append(available[idx])
                break
        else:
            selected.append(available[-1])

    return selected


def generate_pv_candidates(
    n_candidates: int = 6,
    base_params: Optional[dict] = None,
    seed: Optional[int] = None,
    prior_lessons: Optional[list[dict]] = None,
    experiment_memories: Optional[list[dict]] = None,
) -> list[CandidateSpec]:
    """Generate PV candidate parameter variations with realistic priors.

    Uses memory-guided family weighting (CC-BE-2409):
    - Families with promotion history get higher selection weight
    - Families with consistent hard-fails get down-ranked
    - Each candidate tagged with proposal rationale:
      memory-supported, exploratory, recovery, retry-with-correction

    Uses physically-grounded perturbation families bounded to plausible
    improvement magnitudes (CC-BE-2406). Rejects unrealistic cross-parameter
    combinations at generation time.
    """
    rng = random.Random(seed)

    base = dict(base_params or DEFAULT_CELL_PARAMS)
    candidates = []

    # Compute family weights from memory
    weights, family_tags = _compute_family_weights(prior_lessons, experiment_memories)

    # Select families using weighted sampling
    selected_families = _select_families_weighted(
        CANDIDATE_FAMILIES, weights, n_candidates, rng,
    )

    for i, family in enumerate(selected_families):
        params = dict(base)
        description_parts = []
        proposal_tag = family_tags.get(family["family"], PROPOSAL_TAG_EXPLORATORY)

        for param, delta_range in family["perturbations"].items():
            if param == "I_o_ref":
                multiplier = rng.uniform(delta_range[0], delta_range[1])
                params[param] = base.get(param, 1e-10) * multiplier
                description_parts.append(f"{param}*={multiplier:.3f}")
            else:
                delta = rng.uniform(delta_range[0], delta_range[1])
                params[param] = base.get(param, 0) + delta
                description_parts.append(f"{param}+={delta:.4f}")

        # Clamp to physical bounds
        for param, (lo, hi) in PARAM_RANGES.items():
            if param in params:
                params[param] = max(lo, min(hi, params[param]))

        # Cross-parameter plausibility filter
        cross_ok, cross_reasons = _check_cross_parameter_plausibility(params)
        if not cross_ok:
            params = dict(base)
            description_parts = []
            for param, delta_range in family["perturbations"].items():
                if param == "I_o_ref":
                    multiplier = rng.uniform(
                        max(delta_range[0], 0.3),
                        min(delta_range[1], 0.8),
                    )
                    params[param] = base.get(param, 1e-10) * multiplier
                    description_parts.append(f"{param}*={multiplier:.3f}(conservative)")
                else:
                    mid = (delta_range[0] + delta_range[1]) / 2
                    half_span = (delta_range[1] - delta_range[0]) / 4
                    delta = rng.uniform(mid - half_span, mid + half_span)
                    params[param] = base.get(param, 0) + delta
                    description_parts.append(f"{param}+={delta:.4f}(conservative)")
            for param, (lo, hi) in PARAM_RANGES.items():
                if param in params:
                    params[param] = max(lo, min(hi, params[param]))

        candidate = CandidateSpec(
            domain_name="pv_iv",
            title=f"PV {family['family']} variant {i+1}",
            description=", ".join(description_parts),
            parameters=params,
            rationale=f"[{proposal_tag}] {family['rationale']}",
            source="perturbation",
        )
        candidates.append(candidate)

    return candidates


# ---------------------------------------------------------------------------
# Robustness stress evaluation (CC-BE-2407)
# ---------------------------------------------------------------------------

def compute_robustness_profile(
    cell_params: dict,
    baseline_metrics: dict,
) -> dict:
    """Run multi-axis stress sweeps and compute robustness indicators.

    Returns a robustness profile dict with:
      - worst_case_pmax_delta: worst Pmax % drop vs baseline across all conditions
      - worst_case_ff_delta: worst FF % drop vs baseline
      - efficiency_stability: 1 - CV(efficiency) across all sweep points
      - temperature_sensitivity: Pmax range / max across temp sweep
      - irradiance_sensitivity: Pmax range / max across irr sweep
      - combined_fragility: worst-case Pmax drop in combined sweep
      - sweep_data: all sweep points for persistence
    """
    base_pmax = baseline_metrics.get("Pmax", 1)
    base_ff = baseline_metrics.get("fill_factor", 1)

    all_points: list[dict] = []

    # Temperature sweep
    temp_result = run_experiment("temperature_sweep", cell_params)
    temp_sweep = temp_result.raw_data.get("sweep_results", [])
    all_points.extend(temp_sweep)

    # Irradiance sweep
    irr_result = run_experiment("irradiance_sweep", cell_params)
    irr_sweep = irr_result.raw_data.get("sweep_results", [])
    all_points.extend(irr_sweep)

    # Combined stress sweep
    combined_result = run_experiment("combined_sensitivity", cell_params)
    combined_sweep = combined_result.raw_data.get("sweep_results", [])
    all_points.extend(combined_sweep)

    # Compute worst-case deltas
    if not all_points:
        return {
            "worst_case_pmax_delta": 0.0,
            "worst_case_ff_delta": 0.0,
            "efficiency_stability": 0.5,
            "temperature_sensitivity": 0.0,
            "irradiance_sensitivity": 0.0,
            "combined_fragility": 0.0,
            "sweep_data": [],
        }

    pmaxes_all = [p.get("Pmax", 0) for p in all_points if p.get("Pmax", 0) > 0]
    ffs_all = [p.get("fill_factor", 0) for p in all_points if p.get("fill_factor", 0) > 0]
    effs_all = [p.get("efficiency", 0) for p in all_points if p.get("efficiency", 0) > 0]

    # Worst-case Pmax drop (negative = degradation)
    worst_pmax = min(pmaxes_all) if pmaxes_all else 0
    worst_case_pmax_delta = (worst_pmax - base_pmax) / base_pmax if base_pmax > 0 else 0.0

    # Worst-case FF drop
    worst_ff = min(ffs_all) if ffs_all else 0
    worst_case_ff_delta = (worst_ff - base_ff) / base_ff if base_ff > 0 else 0.0

    # Efficiency stability (1 - CV)
    if effs_all and len(effs_all) > 1:
        mean_eff = sum(effs_all) / len(effs_all)
        var_eff = sum((e - mean_eff) ** 2 for e in effs_all) / len(effs_all)
        cv_eff = (var_eff ** 0.5) / mean_eff if mean_eff > 0 else 1.0
        efficiency_stability = max(0.0, min(1.0, 1.0 - cv_eff * 2))
    else:
        efficiency_stability = 0.5

    # Per-sweep sensitivities
    temp_pmaxes = [p.get("Pmax", 0) for p in temp_sweep if p.get("Pmax", 0) > 0]
    temperature_sensitivity = (
        (max(temp_pmaxes) - min(temp_pmaxes)) / max(temp_pmaxes)
        if temp_pmaxes and max(temp_pmaxes) > 0 else 0.0
    )

    irr_pmaxes = [p.get("Pmax", 0) for p in irr_sweep if p.get("Pmax", 0) > 0]
    irradiance_sensitivity = (
        (max(irr_pmaxes) - min(irr_pmaxes)) / max(irr_pmaxes)
        if irr_pmaxes and max(irr_pmaxes) > 0 else 0.0
    )

    comb_pmaxes = [p.get("Pmax", 0) for p in combined_sweep if p.get("Pmax", 0) > 0]
    combined_fragility = (
        (max(comb_pmaxes) - min(comb_pmaxes)) / max(comb_pmaxes)
        if comb_pmaxes and max(comb_pmaxes) > 0 else 0.0
    )

    return {
        "worst_case_pmax_delta": round(worst_case_pmax_delta, 4),
        "worst_case_ff_delta": round(worst_case_ff_delta, 4),
        "efficiency_stability": round(efficiency_stability, 4),
        "temperature_sensitivity": round(temperature_sensitivity, 4),
        "irradiance_sensitivity": round(irradiance_sensitivity, 4),
        "combined_fragility": round(combined_fragility, 4),
        "sweep_data": all_points,
    }


# ---------------------------------------------------------------------------
# PV Scoring (updated CC-BE-2407)
# ---------------------------------------------------------------------------

PV_SCORE_WEIGHTS = {
    "pmax_improvement": 0.25,
    "ff_improvement": 0.15,
    "efficiency_improvement": 0.15,
    "robustness": 0.20,
    "stress_resilience": 0.10,
    "plausibility_penalty": 0.15,
}


def score_pv_candidate(
    candidate_metrics: dict,
    baseline_metrics: dict,
    sweep_results: Optional[list[dict]] = None,
    robustness_profile: Optional[dict] = None,
) -> EvaluationResult:
    """Score a PV candidate against baseline metrics.

    Uses multi-axis stress sweeps for robustness scoring when available.
    Returns EvaluationResult with score components and hard-fail assessment.
    """
    components: dict = {}
    hard_fail = False
    hard_fail_reasons: list[str] = []
    caveats: list[str] = []

    # --- Pmax improvement ---
    base_pmax = baseline_metrics.get("Pmax", 0)
    cand_pmax = candidate_metrics.get("Pmax", 0)
    if base_pmax > 0:
        pmax_delta = (cand_pmax - base_pmax) / base_pmax
        components["pmax_improvement"] = min(1.0, max(0.0, (pmax_delta + 0.05) / 0.25))
    else:
        components["pmax_improvement"] = 0.0

    # Hard fail: Pmax collapsed
    if base_pmax > 0 and cand_pmax < base_pmax * 0.5:
        hard_fail = True
        hard_fail_reasons.append(f"Pmax collapsed: {cand_pmax:.2f}W vs baseline {base_pmax:.2f}W")

    # --- Fill factor improvement ---
    base_ff = baseline_metrics.get("fill_factor", 0)
    cand_ff = candidate_metrics.get("fill_factor", 0)
    if base_ff > 0:
        ff_delta = (cand_ff - base_ff) / base_ff
        components["ff_improvement"] = min(1.0, max(0.0, (ff_delta + 0.02) / 0.10))
    else:
        components["ff_improvement"] = 0.0

    # Hard fail: FF collapsed
    if base_ff > 0 and cand_ff < base_ff * 0.7:
        hard_fail = True
        hard_fail_reasons.append(f"Fill factor collapsed: {cand_ff:.4f} vs baseline {base_ff:.4f}")

    # --- Efficiency improvement ---
    base_eff = baseline_metrics.get("efficiency", 0)
    cand_eff = candidate_metrics.get("efficiency", 0)
    if base_eff > 0:
        eff_delta = (cand_eff - base_eff) / base_eff
        components["efficiency_improvement"] = min(1.0, max(0.0, (eff_delta + 0.03) / 0.15))
    else:
        components["efficiency_improvement"] = 0.0

    # --- Robustness (from sweep data — backward compatible) ---
    if sweep_results and len(sweep_results) > 1:
        pmaxes = [s.get("Pmax", 0) for s in sweep_results if s.get("Pmax", 0) > 0]
        if pmaxes:
            mean_pmax = sum(pmaxes) / len(pmaxes)
            variance = sum((p - mean_pmax) ** 2 for p in pmaxes) / len(pmaxes)
            cv = (variance ** 0.5) / mean_pmax if mean_pmax > 0 else 1.0
            components["robustness"] = max(0.0, min(1.0, 1.0 - cv * 2))
        else:
            components["robustness"] = 0.0
    else:
        components["robustness"] = 0.5  # neutral if no sweep data

    # --- Stress resilience (CC-BE-2407: from robustness profile) ---
    if robustness_profile:
        # Composite stress score: penalize large worst-case drops and fragility
        wc_pmax = robustness_profile.get("worst_case_pmax_delta", 0)
        wc_ff = robustness_profile.get("worst_case_ff_delta", 0)
        eff_stab = robustness_profile.get("efficiency_stability", 0.5)
        fragility = robustness_profile.get("combined_fragility", 0)

        # Worst-case Pmax: 0 at -50% or worse, 1 at 0% or better
        stress_pmax = max(0.0, min(1.0, (wc_pmax + 0.5) / 0.5))
        # Worst-case FF: 0 at -30% or worse, 1 at 0% or better
        stress_ff = max(0.0, min(1.0, (wc_ff + 0.3) / 0.3))
        # Fragility: 0 at 80%+ variation, 1 at <10% variation
        stress_frag = max(0.0, min(1.0, 1.0 - fragility))

        components["stress_resilience"] = round(
            0.4 * stress_pmax + 0.2 * stress_ff + 0.2 * eff_stab + 0.2 * stress_frag, 4
        )

        # Caveats for stress weaknesses
        if wc_pmax < -0.30:
            caveats.append(f"Severe worst-case Pmax drop: {wc_pmax:.1%} under stress")
        elif wc_pmax < -0.15:
            caveats.append(f"Moderate worst-case Pmax drop: {wc_pmax:.1%} under stress")
        if fragility > 0.5:
            caveats.append(f"High combined fragility: {fragility:.1%} Pmax variation across conditions")
        if robustness_profile.get("temperature_sensitivity", 0) > 0.3:
            caveats.append(
                f"Temperature-sensitive: {robustness_profile['temperature_sensitivity']:.1%} "
                "Pmax variation across temperature sweep"
            )
    else:
        components["stress_resilience"] = 0.5  # neutral if no profile

    # --- Plausibility penalty ---
    ok, reasons = check_metrics_plausibility(candidate_metrics)
    if ok:
        components["plausibility_penalty"] = 1.0
    else:
        components["plausibility_penalty"] = 0.0
        caveats.extend(reasons)
        if any("Shockley-Queisser" in r for r in reasons):
            hard_fail = True
            hard_fail_reasons.append("Exceeds Shockley-Queisser limit")

    # --- Final score ---
    final = sum(
        components.get(k, 0) * w
        for k, w in PV_SCORE_WEIGHTS.items()
    )

    return EvaluationResult(
        candidate_id="",  # caller sets
        domain_name="pv_iv",
        score_components=components,
        final_score=round(final, 4),
        hard_fail=hard_fail,
        hard_fail_reasons=hard_fail_reasons,
        caveats=caveats,
    )


# ---------------------------------------------------------------------------
# Caveat generation (CC-BE-2408)
# ---------------------------------------------------------------------------

def generate_candidate_caveats(
    candidate: CandidateSpec,
    evaluation: EvaluationResult,
    baseline_metrics: dict,
    candidate_metrics: dict,
    robustness_profile: Optional[dict] = None,
) -> list[str]:
    """Generate explicit caveats for a promoted or alternate candidate.

    Returns a list of human-readable caveat strings documenting:
    - what changed vs baseline
    - what assumptions drive the gain
    - where the candidate weakens
    - whether gains are concentrated in specific operating regimes
    """
    caveats: list[str] = list(evaluation.caveats)  # start with scoring caveats

    base_pmax = baseline_metrics.get("Pmax", 0)
    cand_pmax = candidate_metrics.get("Pmax", 0)
    base_ff = baseline_metrics.get("fill_factor", 0)
    cand_ff = candidate_metrics.get("fill_factor", 0)
    base_eff = baseline_metrics.get("efficiency", 0)
    cand_eff = candidate_metrics.get("efficiency", 0)

    # What changed
    changed_params = []
    base = DEFAULT_CELL_PARAMS
    for param in ("R_s", "R_sh_ref", "I_L_ref", "I_o_ref", "a_ref"):
        base_val = base.get(param, 0)
        cand_val = candidate.parameters.get(param, base_val)
        if base_val and abs(cand_val - base_val) / max(abs(base_val), 1e-15) > 0.01:
            changed_params.append(f"{param}: {base_val} → {cand_val:.4g}")
    if changed_params:
        caveats.append(f"Parameter changes: {'; '.join(changed_params)}")

    # What assumptions drive the gain
    components = evaluation.score_components
    if components:
        strongest = max(components, key=lambda k: components[k])
        weakest = min(components, key=lambda k: components[k])
        if components[strongest] > 0.7:
            caveats.append(f"Gain concentrated in {strongest} (score={components[strongest]:.2f})")
        if components[weakest] < 0.3:
            caveats.append(f"Weakness in {weakest} (score={components[weakest]:.2f})")

    # Where candidate weakens
    if base_pmax > 0 and cand_pmax < base_pmax:
        caveats.append(f"Pmax decreased: {cand_pmax:.2f}W vs baseline {base_pmax:.2f}W")
    if base_ff > 0 and cand_ff < base_ff:
        caveats.append(f"Fill factor decreased: {cand_ff:.4f} vs baseline {base_ff:.4f}")
    if base_eff > 0 and cand_eff < base_eff:
        caveats.append(f"Efficiency decreased: {cand_eff:.2f}% vs baseline {base_eff:.2f}%")

    # Operating regime concentration
    if robustness_profile:
        temp_sens = robustness_profile.get("temperature_sensitivity", 0)
        irr_sens = robustness_profile.get("irradiance_sensitivity", 0)
        if temp_sens > 0.25:
            caveats.append(
                f"Gains may be STC-concentrated: {temp_sens:.1%} Pmax variation across temperatures"
            )
        if irr_sens > 0.7:
            caveats.append(
                f"Low-light performance concern: {irr_sens:.1%} Pmax variation across irradiance"
            )

    return caveats


# ---------------------------------------------------------------------------
# Full PV optimization loop
# ---------------------------------------------------------------------------

# Alternate threshold: candidate must be within this margin of the
# promotion threshold to qualify as an alternate (CC-BE-2408)
ALTERNATE_MARGIN = 0.05

class PVOptimizationLoop:
    """End-to-end PV optimization loop.

    Generates candidates, runs experiments, scores, promotes/rejects,
    and persists all memory.
    """

    def __init__(
        self,
        repo: Repository,
        n_candidates: int = 6,
        promotion_threshold: float = 0.55,
        base_params: Optional[dict] = None,
        seed: Optional[int] = None,
    ):
        self.repo = repo
        self.n_candidates = n_candidates
        self.promotion_threshold = promotion_threshold
        self.base_params = base_params or dict(DEFAULT_CELL_PARAMS)
        self.seed = seed

    def run(self, run_id: str = "") -> PVLoopResult:
        """Execute one full optimization loop iteration.

        Returns PVLoopResult with all candidates, evaluations, and decisions.
        """
        # Load prior lessons and experiment memory (CC-BE-2409)
        prior_lessons = self.repo.list_idea_memory("pv_iv", limit=50)
        experiment_memories = self.repo.list_experiment_memory("pv_iv", limit=50)

        # 1. Generate baseline
        logger.info("Running baseline experiment...")
        baseline_result = run_experiment("stc_baseline", self.base_params)
        baseline_metrics = baseline_result.metrics

        # 2. Generate candidates (memory-guided)
        logger.info("Generating %d PV candidates...", self.n_candidates)
        candidates = generate_pv_candidates(
            n_candidates=self.n_candidates,
            base_params=self.base_params,
            seed=self.seed,
            prior_lessons=prior_lessons,
            experiment_memories=experiment_memories,
        )

        results: list[PVCandidateResult] = []

        for candidate in candidates:
            candidate.run_id = run_id
            cr = self._evaluate_candidate(candidate, baseline_metrics, run_id)
            results.append(cr)

        # --- Selective promotion policy (CC-BE-2408) ---
        # Sort candidates that passed scoring (not hard-fail) by score
        scorable = [
            r for r in results
            if not r.evaluation.hard_fail and r.evaluation.final_score > 0
        ]
        scorable.sort(key=lambda r: r.evaluation.final_score, reverse=True)

        best = None
        alternate = None
        promoted_count = 0

        for r in scorable:
            if r.evaluation.final_score >= self.promotion_threshold:
                if best is None:
                    # First (highest-scoring) candidate above threshold → promoted
                    best = r
                    r.decision = PromotionDecision.PROMOTED
                    r.candidate.status = CandidateStatus.PROMOTED
                    r.candidate.rejection_reason = ""
                    self.repo.save_domain_candidate(r.candidate)
                    promoted_count += 1

                    # Generate caveats for promoted candidate
                    r.promotion_caveats = generate_candidate_caveats(
                        r.candidate, r.evaluation, baseline_metrics,
                        r.experiment_metrics, r.robustness_profile,
                    )
                elif (
                    alternate is None
                    and r.evaluation.final_score >= self.promotion_threshold - ALTERNATE_MARGIN
                    and r.candidate.rationale != best.candidate.rationale
                ):
                    # One alternate if near threshold AND differentiated family
                    alternate = r
                    r.decision = PromotionDecision.DEFERRED
                    r.candidate.status = CandidateStatus.EVALUATED
                    r.candidate.rejection_reason = "Alternate: near threshold but not best"
                    self.repo.save_domain_candidate(r.candidate)

                    r.promotion_caveats = generate_candidate_caveats(
                        r.candidate, r.evaluation, baseline_metrics,
                        r.experiment_metrics, r.robustness_profile,
                    )
                else:
                    # Additional candidates above threshold → reject (selective)
                    r.decision = PromotionDecision.REJECTED
                    r.candidate.status = CandidateStatus.REJECTED
                    r.candidate.rejection_reason = (
                        f"Score {r.evaluation.final_score:.4f} above threshold "
                        f"but not selected (selective promotion)"
                    )
                    self.repo.save_domain_candidate(r.candidate)

        return PVLoopResult(
            run_id=run_id,
            baseline_metrics=baseline_metrics,
            candidates=results,
            best_promoted=best,
            alternate=alternate,
            total_candidates=len(candidates),
            promoted_count=promoted_count,
            rejected_count=sum(1 for r in results if r.decision == PromotionDecision.REJECTED),
            hard_fail_count=sum(1 for r in results if r.evaluation.hard_fail),
        )

    def _evaluate_candidate(
        self,
        candidate: CandidateSpec,
        baseline_metrics: dict,
        run_id: str,
    ) -> PVCandidateResult:
        """Evaluate a single candidate through the full pipeline."""

        # Physical plausibility check
        ok, reasons = check_physical_plausibility(candidate.parameters)
        if not ok:
            candidate.status = CandidateStatus.HARD_FAIL
            candidate.rejection_reason = "; ".join(reasons)
            self.repo.save_domain_candidate(candidate)
            eval_result = EvaluationResult(
                candidate_id=candidate.id,
                domain_name="pv_iv",
                hard_fail=True,
                hard_fail_reasons=reasons,
            )
            self.repo.save_evaluation_result(eval_result)
            decision = PromotionDecision.REJECTED
            self._persist_memory(candidate, eval_result, decision, {}, [])
            promo = PromotionRecord(
                candidate_id=candidate.id, domain_name="pv_iv",
                decision=decision, evaluation_id=eval_result.id,
                reason=candidate.rejection_reason,
            )
            self.repo.save_promotion_record(promo)
            return PVCandidateResult(
                candidate=candidate, evaluation=eval_result,
                decision=decision, experiment_metrics={}, sweep_data=[],
            )

        # Run STC experiment
        candidate.status = CandidateStatus.RUNNING
        self.repo.save_domain_candidate(candidate)

        stc_result = run_experiment("stc_baseline", candidate.parameters)
        stc_result.candidate_id = candidate.id
        self.repo.save_experiment_result(stc_result)

        if not stc_result.success:
            candidate.status = CandidateStatus.HARD_FAIL
            candidate.rejection_reason = f"STC experiment failed: {stc_result.error_message}"
            self.repo.save_domain_candidate(candidate)
            eval_result = EvaluationResult(
                candidate_id=candidate.id, domain_name="pv_iv",
                hard_fail=True, hard_fail_reasons=[candidate.rejection_reason],
            )
            self.repo.save_evaluation_result(eval_result)
            decision = PromotionDecision.REJECTED
            self._persist_memory(candidate, eval_result, decision, {}, [])
            promo = PromotionRecord(
                candidate_id=candidate.id, domain_name="pv_iv",
                decision=decision, evaluation_id=eval_result.id,
                reason=candidate.rejection_reason,
            )
            self.repo.save_promotion_record(promo)
            return PVCandidateResult(
                candidate=candidate, evaluation=eval_result,
                decision=decision, experiment_metrics={}, sweep_data=[],
            )

        # Run full robustness stress battery (CC-BE-2407)
        robustness = compute_robustness_profile(candidate.parameters, baseline_metrics)
        sweep_data = robustness.get("sweep_data", [])

        # Score with robustness profile
        eval_result = score_pv_candidate(
            stc_result.metrics, baseline_metrics, sweep_data,
            robustness_profile=robustness,
        )
        eval_result.candidate_id = candidate.id
        self.repo.save_evaluation_result(eval_result)

        # Promote/reject decision
        if eval_result.hard_fail:
            decision = PromotionDecision.REJECTED
            candidate.status = CandidateStatus.HARD_FAIL
            candidate.rejection_reason = "; ".join(eval_result.hard_fail_reasons)
        elif eval_result.final_score >= self.promotion_threshold:
            decision = PromotionDecision.PROMOTED
            candidate.status = CandidateStatus.PROMOTED
        else:
            decision = PromotionDecision.REJECTED
            candidate.status = CandidateStatus.REJECTED
            candidate.rejection_reason = f"Score {eval_result.final_score:.4f} below threshold {self.promotion_threshold}"

        candidate.status = CandidateStatus(candidate.status.value)
        self.repo.save_domain_candidate(candidate)

        promo = PromotionRecord(
            candidate_id=candidate.id,
            domain_name="pv_iv",
            decision=decision,
            evaluation_id=eval_result.id,
            reason=candidate.rejection_reason if decision == PromotionDecision.REJECTED else "Score above threshold",
            baseline_score=baseline_metrics.get("Pmax", 0),
            candidate_score=stc_result.metrics.get("Pmax", 0),
        )
        self.repo.save_promotion_record(promo)

        # Persist memory
        self._persist_memory(candidate, eval_result, decision, stc_result.metrics, sweep_data)

        return PVCandidateResult(
            candidate=candidate,
            evaluation=eval_result,
            decision=decision,
            experiment_metrics=stc_result.metrics,
            sweep_data=sweep_data,
            robustness_profile=robustness,
        )

    def _persist_memory(
        self,
        candidate: CandidateSpec,
        evaluation: EvaluationResult,
        decision: PromotionDecision,
        metrics: dict,
        sweep_data: list[dict],
    ) -> None:
        """Persist idea memory and experiment memory."""
        # Determine lesson from outcome
        if evaluation.hard_fail:
            lesson = f"Hard fail: {'; '.join(evaluation.hard_fail_reasons)}"
        elif decision == PromotionDecision.PROMOTED:
            components = evaluation.score_components
            best_component = max(components, key=components.get) if components else "unknown"
            lesson = f"Promoted with score {evaluation.final_score:.4f}. Strongest component: {best_component}"
        else:
            components = evaluation.score_components
            worst_component = min(components, key=components.get) if components else "unknown"
            lesson = f"Rejected (score {evaluation.final_score:.4f}). Weakest component: {worst_component}"

        # Extract family from title
        family = ""
        for fam_def in CANDIDATE_FAMILIES:
            if fam_def["family"] in candidate.title:
                family = fam_def["family"]
                break

        idea = IdeaMemoryEntry(
            domain_name="pv_iv",
            candidate_id=candidate.id,
            candidate_title=candidate.title,
            candidate_family=family,
            rationale=candidate.rationale,
            outcome=decision.value,
            lesson=lesson,
            tags=list(candidate.parameters.keys()) if candidate.parameters else [],
        )
        self.repo.save_idea_memory(idea)

        # Experiment memory
        informative_metrics = []
        weakness = ""
        if metrics:
            informative_metrics = ["Pmax", "fill_factor", "efficiency"]
        if sweep_data:
            informative_metrics.append("temperature_sensitivity")
            # Check for temperature weakness
            pmaxes = [s.get("Pmax", 0) for s in sweep_data]
            if pmaxes and max(pmaxes) > 0:
                sensitivity = (max(pmaxes) - min(pmaxes)) / max(pmaxes)
                if sensitivity > 0.3:
                    weakness = f"High temperature sensitivity: {sensitivity:.2%} Pmax variation across sweep"

        exp_mem = ExperimentMemoryEntry(
            domain_name="pv_iv",
            candidate_id=candidate.id,
            template_name="stc_baseline+temperature_sweep",
            informative_metrics=informative_metrics,
            weakness_exposed=weakness,
            runtime_seconds=0.0,
            reproducibility_score=1.0,  # pvlib is deterministic
        )
        self.repo.save_experiment_memory(exp_mem)


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

class PVCandidateResult:
    """Result of evaluating a single PV candidate."""
    def __init__(
        self,
        candidate: CandidateSpec,
        evaluation: EvaluationResult,
        decision: PromotionDecision,
        experiment_metrics: dict,
        sweep_data: list[dict],
        robustness_profile: Optional[dict] = None,
        promotion_caveats: Optional[list[str]] = None,
    ):
        self.candidate = candidate
        self.evaluation = evaluation
        self.decision = decision
        self.experiment_metrics = experiment_metrics
        self.sweep_data = sweep_data
        self.robustness_profile = robustness_profile or {}
        self.promotion_caveats = promotion_caveats or []


class PVLoopResult:
    """Result of a full PV optimization loop iteration."""
    def __init__(
        self,
        run_id: str,
        baseline_metrics: dict,
        candidates: list[PVCandidateResult],
        best_promoted: Optional[PVCandidateResult],
        total_candidates: int,
        promoted_count: int,
        rejected_count: int,
        hard_fail_count: int,
        alternate: Optional[PVCandidateResult] = None,
    ):
        self.run_id = run_id
        self.baseline_metrics = baseline_metrics
        self.candidates = candidates
        self.best_promoted = best_promoted
        self.alternate = alternate
        self.total_candidates = total_candidates
        self.promoted_count = promoted_count
        self.rejected_count = rejected_count
        self.hard_fail_count = hard_fail_count

    def summary(self) -> dict:
        """Return a summary dict suitable for logging/persistence."""
        summary: dict = {
            "run_id": self.run_id,
            "total_candidates": self.total_candidates,
            "promoted": self.promoted_count,
            "rejected": self.rejected_count,
            "hard_fail": self.hard_fail_count,
            "baseline_pmax": self.baseline_metrics.get("Pmax", 0),
            "best_promoted_title": self.best_promoted.candidate.title if self.best_promoted else None,
            "best_promoted_score": self.best_promoted.evaluation.final_score if self.best_promoted else None,
            "best_promoted_pmax": self.best_promoted.experiment_metrics.get("Pmax", 0) if self.best_promoted else None,
        }
        if self.best_promoted:
            if self.best_promoted.robustness_profile:
                rp = self.best_promoted.robustness_profile
                summary["best_promoted_robustness"] = {
                    k: v for k, v in rp.items() if k != "sweep_data"
                }
            if self.best_promoted.promotion_caveats:
                summary["best_promoted_caveats"] = self.best_promoted.promotion_caveats
        if self.alternate:
            summary["alternate_title"] = self.alternate.candidate.title
            summary["alternate_score"] = self.alternate.evaluation.final_score
            if self.alternate.promotion_caveats:
                summary["alternate_caveats"] = self.alternate.promotion_caveats
        return summary
