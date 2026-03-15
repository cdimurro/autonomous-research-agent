"""Battery optimization loop — end-to-end candidate generation, experiment,
scoring, and promotion for battery ECM + cycle characterization.

Second narrow-domain optimization loop. It:
1. Generates battery candidate parameter variations with realistic priors
2. Runs fixed experiments (baseline cycle, aging, C-rate sweep) via Thevenin ECM
3. Scores candidates against a baseline with robustness across templates
4. Applies hard-fail gates and generates caveats
5. Promotes or rejects with conservative, selective policy
6. Persists idea memory and experiment memory
7. Uses memory to guide future proposals
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from .battery_domain import (
    DEFAULT_CELL_PARAMS,
    EXPERIMENT_TEMPLATES,
    check_metrics_plausibility,
    check_physical_plausibility,
    run_experiment,
)
from .db import Repository
from .domain_models import (
    CandidateSpec,
    CandidateStatus,
    EvaluationResult,
    ExperimentMemoryEntry,
    IdeaMemoryEntry,
    PromotionDecision,
    PromotionRecord,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Candidate generation — realistic priors
# ---------------------------------------------------------------------------

# Bounded parameter ranges for Li-ion NMC cells.
# Tightened to realistic commercial-cell values based on published
# 18650/21700 datasheet ranges (Sony VTC6, Samsung 30Q, LG MJ1, Panasonic
# NCR18650B, Samsung 50E 21700).
#
# Rationale for each bound:
#   capacity_ah:          2.0–5.5 Ah   (18650: 2.0–3.5, 21700: 4.0–5.0)
#                         Floor raised from 1.5: sub-2Ah NMC cells are legacy
#   R0_mohm:              12–80 mOhm   (fresh: 15–40, aged: 50–80)
#                         Floor raised from 10: sub-12 impossible without
#                         tab-less design; cap lowered from 100: >80 is EOL
#   R1_mohm:              5–50 mOhm    (fresh: 8–20, aged: 25–50)
#                         Cap lowered from 80: >50 is extreme degradation
#   C1_F:                 200–1500 F   (typical: 300–800)
#                         Tightened both ends for realistic RC dynamics
#   coulombic_eff:        0.97–0.9995  (good cell: 0.995+, best: 0.9995)
#                         Floor raised from 0.95: sub-97% indicates cell defect
#                         Ceiling raised to 0.9995: best-in-class NMC
#   fade_rate_per_cycle:  0.0001–0.003 (0.01–0.3% per cycle)
#                         Cap lowered from 0.005: >0.3%/cycle is catastrophic
PARAM_RANGES = {
    "capacity_ah": (2.0, 5.5),
    "R0_mohm": (12.0, 80.0),
    "R1_mohm": (5.0, 50.0),
    "C1_F": (200.0, 1500.0),
    "coulombic_eff": (0.97, 0.9995),
    "fade_rate_per_cycle": (0.0001, 0.003),
}

# Commercial cell reference data for grounding candidate generation.
# Each entry represents a real published cell specification.
# Used as anchors for plausibility — candidates should be interpretable
# relative to these references.
COMMERCIAL_CELL_REFERENCES = [
    {
        "name": "Sony_VTC6_18650",
        "capacity_ah": 3.0, "R0_mohm": 30.0, "R1_mohm": 15.0,
        "coulombic_eff": 0.995, "fade_rate_per_cycle": 0.0005,
        "notes": "Baseline NMC 18650, balanced performance",
    },
    {
        "name": "Samsung_50E_21700",
        "capacity_ah": 5.0, "R0_mohm": 35.0, "R1_mohm": 18.0,
        "coulombic_eff": 0.996, "fade_rate_per_cycle": 0.0004,
        "notes": "High-capacity 21700, moderate resistance",
    },
    {
        "name": "Samsung_30Q_18650",
        "capacity_ah": 3.0, "R0_mohm": 22.0, "R1_mohm": 12.0,
        "coulombic_eff": 0.997, "fade_rate_per_cycle": 0.0003,
        "notes": "Low-resistance NMC 18650, good rate capability",
    },
    {
        "name": "LG_MJ1_18650",
        "capacity_ah": 3.5, "R0_mohm": 40.0, "R1_mohm": 20.0,
        "coulombic_eff": 0.994, "fade_rate_per_cycle": 0.0006,
        "notes": "High-capacity 18650, trades resistance for capacity",
    },
]

# Candidate families with physically-grounded perturbation bounds.
# Each family represents a specific cell-design improvement strategy.
# Perturbation magnitudes are bounded to what is achievable through
# realistic manufacturing or chemistry changes.
CANDIDATE_FAMILIES = [
    {
        "family": "reduced_resistance",
        "rationale": "Lower R0/R1 via improved electrolyte conductivity or "
                     "tab-less electrode design reduces ohmic losses. "
                     "Bounded: 3–10 mOhm R0 reduction is achievable via "
                     "electrolyte optimization (e.g., LiPF6 concentration tuning)",
        "perturbations": {"R0_mohm": (-10.0, -3.0), "R1_mohm": (-6.0, -1.5)},
        "tradeoff_risk": "Lower R0 may indicate thinner separator → safety concern",
    },
    {
        "family": "improved_capacity",
        "rationale": "Higher capacity via silicon-graphite blended anode or "
                     "higher Ni-content cathode increases energy density. "
                     "Bounded: 0.1–0.4 Ah gain is realistic for incremental "
                     "active material improvements",
        "perturbations": {"capacity_ah": (0.1, 0.4)},
        "tradeoff_risk": "Higher capacity often trades cycle life (higher Ni = faster fade)",
    },
    {
        "family": "reduced_fade",
        "rationale": "Lower fade rate via electrolyte additives (FEC, VC) or "
                     "atomic layer deposition coatings improves SEI stability. "
                     "Bounded: 0.01–0.02%/cycle reduction is realistic",
        "perturbations": {"fade_rate_per_cycle": (-0.0002, -0.0001)},
        "tradeoff_risk": "Additives may increase impedance or reduce rate capability",
    },
    {
        "family": "improved_efficiency",
        "rationale": "Higher coulombic efficiency via reduced parasitic reactions "
                     "(improved electrolyte purity, surface coatings). "
                     "Bounded: 0.1–0.3% improvement is realistic",
        "perturbations": {"coulombic_eff": (0.001, 0.003)},
        "tradeoff_risk": "Marginal CE gains may not survive high-temperature operation",
    },
    {
        "family": "combined_moderate",
        "rationale": "Co-optimized resistance reduction and fade improvement "
                     "reflecting a multi-lever cell redesign (electrolyte + coating). "
                     "Each lever kept conservative: R0 -2 to -6 mOhm, fade -0.005 to -0.015%/cycle",
        "perturbations": {"R0_mohm": (-6.0, -2.0), "fade_rate_per_cycle": (-0.00015, -0.00005)},
        "tradeoff_risk": "Multi-lever changes harder to attribute; interaction effects possible",
    },
    {
        "family": "bounded_aggressive",
        "rationale": "Near-best-in-class across R0, capacity, and fade — "
                     "represents what the best commercial cells achieve. "
                     "Bounded: Samsung 30Q-class resistance + modest capacity gain + good fade",
        "perturbations": {
            "R0_mohm": (-12.0, -6.0),
            "capacity_ah": (0.15, 0.5),
            "fade_rate_per_cycle": (-0.0002, -0.0001),
        },
        "tradeoff_risk": "Simultaneously achieving all three is rare; likely requires "
                         "advanced manufacturing (tab-less + high-Ni + premium electrolyte)",
    },
]


def _check_cross_parameter_plausibility(params: dict) -> tuple[bool, list[str]]:
    """Reject unrealistic parameter *combinations* at generation time.

    These checks encode correlations between cell parameters that reflect
    real Li-ion cell physics. A candidate that violates these constraints
    is not just unlikely — it is physically contradictory.
    """
    reasons: list[str] = []

    r0 = params.get("R0_mohm", 30.0)
    r1 = params.get("R1_mohm", 15.0)
    fade = params.get("fade_rate_per_cycle", 0.0005)
    cap = params.get("capacity_ah", 3.0)
    coul = params.get("coulombic_eff", 0.995)

    # 1. Low resistance + high fade is contradictory:
    #    low-resistance cells have stable, well-formed interfaces that
    #    don't degrade quickly.
    if r0 < 15.0 and fade > 0.002:
        reasons.append(
            f"Contradictory: low R0 ({r0:.1f} mOhm) with high fade ({fade*100:.2f}%/cycle) — "
            "low-resistance cells typically have stable interfaces"
        )

    # 2. High capacity + low coulombic efficiency is contradictory:
    #    high-capacity cells need high CE to avoid thermal runaway from
    #    parasitic heat generation.
    if cap > 4.5 and coul < 0.98:
        reasons.append(
            f"Contradictory: high capacity ({cap:.1f} Ah) with low coulombic efficiency "
            f"({coul*100:.1f}%) — high-capacity cells need high efficiency for thermal safety"
        )

    # 3. Very low R0 with very high R1 is contradictory:
    #    If ohmic resistance is very low (good contacts), polarization
    #    resistance should not be extremely high (implies poor ion transport,
    #    which would also raise ohmic resistance).
    if r0 < 15.0 and r1 > 35.0:
        reasons.append(
            f"Contradictory: very low R0 ({r0:.1f} mOhm) with high R1 ({r1:.1f} mOhm) — "
            "good ohmic contacts (low R0) imply reasonable ion transport (moderate R1)"
        )

    # 4. High capacity + low fade + low resistance is aspirational:
    #    This combination is rare but not contradictory — represents
    #    best-in-class manufacturing. We allow it but the bounded_aggressive
    #    family's tradeoff_risk documents the rarity.

    # 5. High capacity tends to increase R0 (thicker electrodes):
    #    A 5+ Ah cell with sub-15 mOhm R0 is extremely rare outside
    #    tab-less designs.
    if cap > 4.5 and r0 < 15.0:
        reasons.append(
            f"Unlikely: high capacity ({cap:.1f} Ah) with very low R0 ({r0:.1f} mOhm) — "
            "thick electrodes for high capacity increase ionic path length and R0"
        )

    # 6. Very high fade with high coulombic efficiency is contradictory:
    #    Rapid capacity fade usually comes with increased side reactions
    #    (lower CE), not perfect CE.
    if fade > 0.002 and coul > 0.998:
        reasons.append(
            f"Contradictory: high fade ({fade*100:.2f}%/cycle) with near-perfect CE "
            f"({coul*100:.2f}%) — rapid fade implies side reactions that lower CE"
        )

    return len(reasons) == 0, reasons


# Proposal rationale tags
PROPOSAL_TAG_MEMORY = "memory-supported"
PROPOSAL_TAG_EXPLORATORY = "exploratory"
PROPOSAL_TAG_RECOVERY = "recovery"
PROPOSAL_TAG_RETRY = "retry-with-correction"
PROPOSAL_TAG_STRESS_INFORMED = "stress-informed"


def _compute_family_weights(
    prior_lessons: Optional[list[dict]],
    experiment_memories: Optional[list[dict]] = None,
) -> tuple[dict[str, float], dict[str, str]]:
    """Compute per-family selection weights from idea memory and experiment memory.

    Uses two memory sources:
    1. IdeaMemory (prior_lessons): outcome-based weighting (promoted/rejected/hard_fail)
    2. ExperimentMemory (experiment_memories): weakness-based penalization

    Families with stress fragility or exposed weaknesses get additional
    down-weighting so the loop steers toward robust candidates.
    """
    weights: dict[str, float] = {f["family"]: 1.0 for f in CANDIDATE_FAMILIES}
    tags: dict[str, str] = {f["family"]: PROPOSAL_TAG_EXPLORATORY for f in CANDIDATE_FAMILIES}

    if not prior_lessons and not experiment_memories:
        return weights, tags

    # --- Phase 1: Outcome-based weighting from IdeaMemory ---
    family_stats: dict[str, dict] = {}
    if prior_lessons:
        for lesson in prior_lessons:
            fam = lesson.get("candidate_family", "")
            outcome = lesson.get("outcome", "")
            if not fam:
                continue
            stats = family_stats.setdefault(
                fam, {"promoted": 0, "rejected": 0, "hard_fail": 0, "total": 0}
            )
            stats["total"] += 1
            if outcome == "promoted":
                stats["promoted"] += 1
            elif outcome == "hard_fail":
                stats["hard_fail"] += 1
            elif outcome == "rejected":
                stats["rejected"] += 1

    for fam, stats in family_stats.items():
        if fam not in weights:
            continue
        total = stats["total"]
        if total == 0:
            continue

        promote_rate = stats["promoted"] / total
        hard_fail_rate = stats["hard_fail"] / total

        if hard_fail_rate == 1.0:
            weights[fam] = 0.1
            tags[fam] = PROPOSAL_TAG_RETRY
        elif hard_fail_rate > 0.5:
            weights[fam] = 0.3
            tags[fam] = PROPOSAL_TAG_RETRY
        elif promote_rate > 0:
            weights[fam] = 1.0 + promote_rate
            tags[fam] = PROPOSAL_TAG_MEMORY
        elif stats["rejected"] == total:
            weights[fam] = 0.5
            tags[fam] = PROPOSAL_TAG_RECOVERY

    # --- Phase 2: Weakness-based penalization from ExperimentMemory ---
    if experiment_memories:
        weakness_counts: dict[str, int] = {}
        stress_fragile: dict[str, int] = {}
        for mem in experiment_memories:
            cid = mem.get("candidate_id", "")
            weakness = mem.get("weakness_exposed", "")
            if not weakness:
                continue
            # Map candidate back to family via idea memory
            fam = _candidate_id_to_family(cid, prior_lessons)
            if fam:
                weakness_counts[fam] = weakness_counts.get(fam, 0) + 1
                if "stress" in weakness.lower() or "fragile" in weakness.lower():
                    stress_fragile[fam] = stress_fragile.get(fam, 0) + 1

        for fam, count in weakness_counts.items():
            if fam in weights and count >= 2:
                # Repeated weakness → down-weight further
                weights[fam] *= 0.7
                if fam in stress_fragile and stress_fragile[fam] >= 2:
                    weights[fam] *= 0.5
                    tags[fam] = PROPOSAL_TAG_STRESS_INFORMED

    return weights, tags


def _candidate_id_to_family(
    candidate_id: str,
    prior_lessons: Optional[list[dict]],
) -> str:
    """Look up the family of a candidate from prior lessons."""
    if not prior_lessons:
        return ""
    for lesson in prior_lessons:
        if lesson.get("candidate_id", "") == candidate_id:
            return lesson.get("candidate_family", "")
    return ""


def _select_families_weighted(
    families: list[dict],
    weights: dict[str, float],
    n: int,
    rng: random.Random,
) -> list[dict]:
    """Select n families using weighted sampling."""
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


def generate_battery_candidates(
    n_candidates: int = 6,
    base_params: Optional[dict] = None,
    seed: Optional[int] = None,
    prior_lessons: Optional[list[dict]] = None,
    experiment_memories: Optional[list[dict]] = None,
) -> list[CandidateSpec]:
    """Generate battery candidate parameter variations with realistic priors.

    Uses memory-guided family weighting and physically-grounded perturbation
    families bounded to plausible improvement magnitudes.
    """
    rng = random.Random(seed)
    base = dict(base_params or DEFAULT_CELL_PARAMS)
    candidates = []

    weights, family_tags = _compute_family_weights(prior_lessons, experiment_memories)
    selected_families = _select_families_weighted(
        CANDIDATE_FAMILIES, weights, n_candidates, rng,
    )

    for i, family in enumerate(selected_families):
        params = dict(base)
        description_parts = []
        proposal_tag = family_tags.get(family["family"], PROPOSAL_TAG_EXPLORATORY)

        for param, delta_range in family["perturbations"].items():
            delta = rng.uniform(delta_range[0], delta_range[1])
            params[param] = base.get(param, 0) + delta
            description_parts.append(f"{param}+={delta:.6f}")

        # Clamp to physical bounds
        for param, (lo, hi) in PARAM_RANGES.items():
            if param in params:
                params[param] = max(lo, min(hi, params[param]))

        # Cross-parameter plausibility filter
        cross_ok, cross_reasons = _check_cross_parameter_plausibility(params)
        if not cross_ok:
            # Regenerate with conservative perturbations
            params = dict(base)
            description_parts = []
            for param, delta_range in family["perturbations"].items():
                mid = (delta_range[0] + delta_range[1]) / 2
                half_span = (delta_range[1] - delta_range[0]) / 4
                delta = rng.uniform(mid - half_span, mid + half_span)
                params[param] = base.get(param, 0) + delta
                description_parts.append(f"{param}+={delta:.6f}(conservative)")
            for param, (lo, hi) in PARAM_RANGES.items():
                if param in params:
                    params[param] = max(lo, min(hi, params[param]))

        candidate = CandidateSpec(
            domain_name="battery_ecm",
            title=f"Battery {family['family']} variant {i+1}",
            description=", ".join(description_parts),
            parameters=params,
            rationale=f"[{proposal_tag}] {family['rationale']}",
            source="perturbation",
        )
        candidates.append(candidate)

    return candidates


# ---------------------------------------------------------------------------
# Battery Scoring (CC-BE-2414)
# ---------------------------------------------------------------------------

BATTERY_SCORE_WEIGHTS = {
    "capacity_retention": 0.15,
    "coulombic_improvement": 0.10,
    "resistance_improvement": 0.15,
    "fade_improvement": 0.10,
    "rate_capability": 0.10,
    "robustness": 0.10,
    "stress_resilience": 0.15,
    "plausibility_penalty": 0.15,
}


def compute_robustness_profile(
    cell_params: dict,
    baseline_metrics: dict,
) -> dict:
    """Run multi-template stress evaluation and compute robustness indicators.

    Runs 5 stress experiments:
    1. C-rate sweep (C/3 to 3C) — rate capability
    2. Thermal sensitivity (10–55C) — thermal fragility
    3. Cycle aging (50 cycles @ 1C/25C) — standard fade
    4. Fast-charge stress (20 cycles @ 2C) — fast-charge penalty
    5. Thermal stress aging (20 cycles @ 1C/45C) — accelerated thermal degradation
    """
    base_cap = baseline_metrics.get("discharge_capacity", 1)

    # C-rate sweep
    crate_result = run_experiment("crate_sweep", cell_params)
    crate_data = crate_result.raw_data.get("cycle_results", [])

    # Thermal sensitivity
    thermal_result = run_experiment("thermal_sensitivity", cell_params)
    thermal_data = thermal_result.raw_data.get("cycle_results", [])

    # Cycle aging (standard)
    aging_result = run_experiment("cycle_aging", cell_params)

    # Fast-charge stress (CC-BE-2417)
    fast_charge_result = run_experiment("fast_charge_stress", cell_params)

    # Thermal stress aging (CC-BE-2417)
    thermal_stress_result = run_experiment("thermal_stress_aging", cell_params)

    all_caps = []
    for r in crate_data + thermal_data:
        if r.get("success", True) and r.get("discharge_capacity", 0) > 0:
            all_caps.append(r["discharge_capacity"])

    if not all_caps:
        return {
            "worst_case_capacity_delta": 0.0,
            "crate_sensitivity": 0.0,
            "thermal_sensitivity": 0.0,
            "capacity_retention": 100.0,
            "fade_rate": 0.0,
            "fast_charge_fade_rate": 0.0,
            "fast_charge_penalty_pct": 0.0,
            "thermal_stress_fade_rate": 0.0,
            "thermal_stress_penalty_pct": 0.0,
            "worst_stress_retention": 100.0,
            "sweep_data": [],
        }

    worst_cap = min(all_caps)
    worst_delta = (worst_cap - base_cap) / base_cap if base_cap > 0 else 0.0

    # C-rate sensitivity
    crate_caps = [r["discharge_capacity"] for r in crate_data if r.get("success", True) and r.get("discharge_capacity", 0) > 0]
    crate_sensitivity = ((max(crate_caps) - min(crate_caps)) / max(crate_caps)) if crate_caps and max(crate_caps) > 0 else 0.0

    # Thermal sensitivity
    thermal_caps = [r["discharge_capacity"] for r in thermal_data if r.get("success", True) and r.get("discharge_capacity", 0) > 0]
    thermal_sensitivity = ((max(thermal_caps) - min(thermal_caps)) / max(thermal_caps)) if thermal_caps and max(thermal_caps) > 0 else 0.0

    # Fast-charge stress metrics
    fc_fade = fast_charge_result.metrics.get("stress_fade_rate", 0.0)
    fc_penalty = fast_charge_result.metrics.get("stress_penalty_pct", 0.0)
    fc_retention = fast_charge_result.metrics.get("capacity_retention", 100.0)

    # Thermal stress metrics
    ts_fade = thermal_stress_result.metrics.get("stress_fade_rate", 0.0)
    ts_penalty = thermal_stress_result.metrics.get("stress_penalty_pct", 0.0)
    ts_retention = thermal_stress_result.metrics.get("capacity_retention", 100.0)

    # Worst-case retention across all stress scenarios
    standard_retention = aging_result.metrics.get("capacity_retention", 100.0)
    worst_stress_retention = min(standard_retention, fc_retention, ts_retention)

    return {
        "worst_case_capacity_delta": round(worst_delta, 4),
        "crate_sensitivity": round(crate_sensitivity, 4),
        "thermal_sensitivity": round(thermal_sensitivity, 4),
        "capacity_retention": standard_retention,
        "fade_rate": aging_result.metrics.get("fade_rate", 0.0),
        "fast_charge_fade_rate": round(fc_fade, 4),
        "fast_charge_penalty_pct": round(fc_penalty, 4),
        "thermal_stress_fade_rate": round(ts_fade, 4),
        "thermal_stress_penalty_pct": round(ts_penalty, 4),
        "worst_stress_retention": round(worst_stress_retention, 4),
        "sweep_data": crate_data + thermal_data,
    }


def score_battery_candidate(
    candidate_metrics: dict,
    baseline_metrics: dict,
    robustness_profile: Optional[dict] = None,
) -> EvaluationResult:
    """Score a battery candidate against baseline metrics."""
    components: dict = {}
    hard_fail = False
    hard_fail_reasons: list[str] = []
    caveats: list[str] = []

    # --- Capacity retention ---
    if robustness_profile and "capacity_retention" in robustness_profile:
        ret = robustness_profile["capacity_retention"]
        # 100% → 1.0, 80% → 0.5, 60% → 0.0
        components["capacity_retention"] = max(0.0, min(1.0, (ret - 60.0) / 40.0))
        if ret < 50.0:
            hard_fail = True
            hard_fail_reasons.append(f"Capacity retention {ret:.1f}% below 50% after cycling")
    else:
        components["capacity_retention"] = 0.5

    # --- Coulombic efficiency improvement ---
    base_coul = baseline_metrics.get("coulombic_efficiency", 99.0)
    cand_coul = candidate_metrics.get("coulombic_efficiency", 0)
    if base_coul > 0:
        coul_delta = cand_coul - base_coul
        components["coulombic_improvement"] = max(0.0, min(1.0, (coul_delta + 1.0) / 3.0))
    else:
        components["coulombic_improvement"] = 0.0

    if cand_coul < 90.0 and cand_coul > 0:
        hard_fail = True
        hard_fail_reasons.append(f"Coulombic efficiency {cand_coul:.1f}% below 90%")

    # --- Resistance improvement ---
    base_r = baseline_metrics.get("internal_resistance", 45.0)
    cand_r = candidate_metrics.get("internal_resistance", 0)
    if base_r > 0 and cand_r > 0:
        r_delta = (base_r - cand_r) / base_r  # positive = improvement
        components["resistance_improvement"] = max(0.0, min(1.0, (r_delta + 0.05) / 0.30))
    else:
        components["resistance_improvement"] = 0.0

    if cand_r > 200:
        hard_fail = True
        hard_fail_reasons.append(f"Internal resistance {cand_r:.1f} mOhm exceeds 200 mOhm limit")

    # --- Fade improvement ---
    if robustness_profile and "fade_rate" in robustness_profile:
        base_fade = 0.05  # baseline default: 0.05%/cycle
        cand_fade = robustness_profile["fade_rate"]
        fade_delta = base_fade - cand_fade  # positive = improvement
        components["fade_improvement"] = max(0.0, min(1.0, (fade_delta + 0.01) / 0.04))
    else:
        components["fade_improvement"] = 0.5

    # --- Rate capability ---
    if robustness_profile and "crate_sensitivity" in robustness_profile:
        cs = robustness_profile["crate_sensitivity"]
        # Lower sensitivity is better: 0% → 1.0, 30% → 0.4, 60% → 0.0
        components["rate_capability"] = max(0.0, min(1.0, 1.0 - cs * 1.5))
    else:
        components["rate_capability"] = 0.5

    # --- Robustness (across all stress points) ---
    if robustness_profile and "worst_case_capacity_delta" in robustness_profile:
        wc = robustness_profile["worst_case_capacity_delta"]
        # 0% drop → 1.0, -25% → 0.5, -50% → 0.0
        components["robustness"] = max(0.0, min(1.0, (wc + 0.5) / 0.5))
        if wc < -0.30:
            caveats.append(f"Severe worst-case capacity drop: {wc:.1%} under stress")
        ts = robustness_profile.get("thermal_sensitivity", 0)
        if ts > 0.15:
            caveats.append(f"Thermal sensitivity: {ts:.1%} capacity variation across temperatures")
    else:
        components["robustness"] = 0.5

    # --- Stress resilience (fast-charge + thermal stress) ---
    if robustness_profile and "worst_stress_retention" in robustness_profile:
        wsr = robustness_profile["worst_stress_retention"]
        # 100% → 1.0, 90% → 0.75, 70% → 0.25, 50% → 0.0
        components["stress_resilience"] = max(0.0, min(1.0, (wsr - 50.0) / 50.0))

        fc_fade = robustness_profile.get("fast_charge_fade_rate", 0)
        ts_fade = robustness_profile.get("thermal_stress_fade_rate", 0)
        fc_penalty = robustness_profile.get("fast_charge_penalty_pct", 0)
        ts_penalty = robustness_profile.get("thermal_stress_penalty_pct", 0)

        if fc_fade > 0.08:
            caveats.append(
                f"Fast-charge fragility: {fc_fade:.3f}%/cycle fade at 2C "
                f"(penalty {fc_penalty:.1f}% vs 1C baseline)"
            )
        if ts_fade > 0.08:
            caveats.append(
                f"Thermal stress fragility: {ts_fade:.3f}%/cycle fade at 45C "
                f"(penalty {ts_penalty:.1f}% vs 25C baseline)"
            )
        if wsr < 80.0:
            hard_fail = True
            hard_fail_reasons.append(
                f"Worst-case stress retention {wsr:.1f}% below 80% — "
                "candidate is fragile under realistic operating conditions"
            )
    else:
        components["stress_resilience"] = 0.5

    # --- Plausibility penalty ---
    ok, reasons = check_metrics_plausibility(candidate_metrics)
    if ok:
        components["plausibility_penalty"] = 1.0
    else:
        components["plausibility_penalty"] = 0.0
        caveats.extend(reasons)
        hard_fail = True
        hard_fail_reasons.extend(reasons)

    # --- Final score ---
    final = sum(
        components.get(k, 0) * w
        for k, w in BATTERY_SCORE_WEIGHTS.items()
    )

    return EvaluationResult(
        candidate_id="",
        domain_name="battery_ecm",
        score_components=components,
        final_score=round(final, 4),
        hard_fail=hard_fail,
        hard_fail_reasons=hard_fail_reasons,
        caveats=caveats,
    )


# ---------------------------------------------------------------------------
# Caveat generation
# ---------------------------------------------------------------------------

def generate_candidate_caveats(
    candidate: CandidateSpec,
    evaluation: EvaluationResult,
    baseline_metrics: dict,
    candidate_metrics: dict,
    robustness_profile: Optional[dict] = None,
) -> list[str]:
    """Generate explicit decision-grade caveats for a promoted or alternate candidate.

    Caveats cover:
    1. What parameters changed and by how much
    2. Where score gains are concentrated vs weak
    3. Whether fast-charge or thermal stress erodes the benefit
    4. Whether gains are regime-specific (only at 1C/25C)
    5. Degradation warnings vs baseline
    6. Tradeoff risk from the candidate's family
    """
    caveats: list[str] = list(evaluation.caveats)

    # 1. What changed
    changed_params = []
    base = DEFAULT_CELL_PARAMS
    for param in ("R0_mohm", "R1_mohm", "capacity_ah", "coulombic_eff", "fade_rate_per_cycle", "C1_F"):
        base_val = base.get(param, 0)
        cand_val = candidate.parameters.get(param, base_val)
        if base_val and abs(cand_val - base_val) / max(abs(base_val), 1e-15) > 0.01:
            pct = (cand_val - base_val) / abs(base_val) * 100
            changed_params.append(f"{param}: {base_val} → {cand_val:.4g} ({pct:+.1f}%)")
    if changed_params:
        caveats.append(f"Parameter changes: {'; '.join(changed_params)}")

    # 2. Score concentration and weakness
    components = evaluation.score_components
    if components:
        strongest = max(components, key=lambda k: components[k])
        weakest = min(components, key=lambda k: components[k])
        if components[strongest] > 0.7:
            caveats.append(f"Gain concentrated in {strongest} (score={components[strongest]:.2f})")
        if components[weakest] < 0.3:
            caveats.append(f"Weakness in {weakest} (score={components[weakest]:.2f})")

    # 3. Stress-informed caveats: does fast-charge or thermal stress erode the benefit?
    if robustness_profile:
        fc_fade = robustness_profile.get("fast_charge_fade_rate", 0)
        standard_fade = robustness_profile.get("fade_rate", 0)
        if fc_fade > 0 and standard_fade > 0 and fc_fade > standard_fade * 1.5:
            caveats.append(
                f"Fast-charge erodes benefit: fade at 2C ({fc_fade:.4f}%/cycle) is "
                f"{fc_fade/standard_fade:.1f}x worse than standard ({standard_fade:.4f}%/cycle)"
            )
        ts_fade = robustness_profile.get("thermal_stress_fade_rate", 0)
        if ts_fade > 0 and standard_fade > 0 and ts_fade > standard_fade * 1.5:
            caveats.append(
                f"Thermal stress erodes benefit: fade at 45C ({ts_fade:.4f}%/cycle) is "
                f"{ts_fade/standard_fade:.1f}x worse than standard ({standard_fade:.4f}%/cycle)"
            )
        wsr = robustness_profile.get("worst_stress_retention", 100)
        standard_ret = robustness_profile.get("capacity_retention", 100)
        if wsr < standard_ret - 5.0:
            caveats.append(
                f"Stress-sensitive: worst retention under stress ({wsr:.1f}%) vs "
                f"standard aging ({standard_ret:.1f}%) — gains may be regime-specific"
            )

    # 4. Degradation warnings
    base_cap = baseline_metrics.get("discharge_capacity", 0)
    cand_cap = candidate_metrics.get("discharge_capacity", 0)
    if base_cap > 0 and cand_cap < base_cap * 0.95:
        caveats.append(f"Capacity decreased: {cand_cap:.3f} Ah vs baseline {base_cap:.3f} Ah")

    base_coul = baseline_metrics.get("coulombic_efficiency", 0)
    cand_coul = candidate_metrics.get("coulombic_efficiency", 0)
    if base_coul > 0 and cand_coul < base_coul - 0.5:
        caveats.append(f"Coulombic efficiency decreased: {cand_coul:.2f}% vs baseline {base_coul:.2f}%")

    # 5. Family tradeoff risk
    for fam_def in CANDIDATE_FAMILIES:
        if fam_def["family"] in candidate.title:
            caveats.append(f"Tradeoff risk ({fam_def['family']}): {fam_def['tradeoff_risk']}")
            break

    return caveats


def generate_rejection_reason(
    candidate: CandidateSpec,
    evaluation: EvaluationResult,
    promotion_threshold: float,
    robustness_profile: Optional[dict] = None,
) -> str:
    """Generate an explicit rejection reason for a near-miss or rejected candidate."""
    score = evaluation.final_score
    gap = promotion_threshold - score

    if evaluation.hard_fail:
        return f"Hard fail: {'; '.join(evaluation.hard_fail_reasons)}"

    components = evaluation.score_components or {}
    parts = [f"Score {score:.4f} below threshold {promotion_threshold:.2f} (gap: {gap:.4f})"]

    if components:
        weakest = min(components, key=lambda k: components[k])
        parts.append(f"weakest component: {weakest} ({components[weakest]:.2f})")

    if robustness_profile:
        wsr = robustness_profile.get("worst_stress_retention", 100)
        if wsr < 90:
            parts.append(f"stress-fragile (worst retention {wsr:.1f}%)")

    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Full battery optimization loop
# ---------------------------------------------------------------------------

ALTERNATE_MARGIN = 0.05


class BatteryCandidateResult:
    """Result of evaluating a single battery candidate."""
    def __init__(
        self,
        candidate: CandidateSpec,
        evaluation: EvaluationResult,
        decision: PromotionDecision,
        experiment_metrics: dict,
        robustness_profile: Optional[dict] = None,
        promotion_caveats: Optional[list[str]] = None,
    ):
        self.candidate = candidate
        self.evaluation = evaluation
        self.decision = decision
        self.experiment_metrics = experiment_metrics
        self.robustness_profile = robustness_profile or {}
        self.promotion_caveats = promotion_caveats or []


class BatteryLoopResult:
    """Result of a full battery optimization loop iteration."""
    def __init__(
        self,
        run_id: str,
        baseline_metrics: dict,
        candidates: list[BatteryCandidateResult],
        best_promoted: Optional[BatteryCandidateResult],
        total_candidates: int,
        promoted_count: int,
        rejected_count: int,
        hard_fail_count: int,
        alternate: Optional[BatteryCandidateResult] = None,
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
        summary: dict = {
            "run_id": self.run_id,
            "total_candidates": self.total_candidates,
            "promoted": self.promoted_count,
            "rejected": self.rejected_count,
            "hard_fail": self.hard_fail_count,
            "baseline_capacity": self.baseline_metrics.get("discharge_capacity", 0),
            "baseline_resistance": self.baseline_metrics.get("internal_resistance", 0),
            "best_promoted_title": self.best_promoted.candidate.title if self.best_promoted else None,
            "best_promoted_score": self.best_promoted.evaluation.final_score if self.best_promoted else None,
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
        return summary


class BatteryOptimizationLoop:
    """End-to-end battery optimization loop."""

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

    def run(self, run_id: str = "") -> BatteryLoopResult:
        """Execute one full optimization loop iteration."""
        prior_lessons = self.repo.list_idea_memory("battery_ecm", limit=50)
        experiment_memories = self.repo.list_experiment_memory("battery_ecm", limit=50)

        # 1. Generate baseline
        logger.info("Running baseline battery experiment...")
        baseline_result = run_experiment("baseline_cycle", self.base_params)
        baseline_metrics = baseline_result.metrics

        # 2. Generate candidates
        logger.info("Generating %d battery candidates...", self.n_candidates)
        candidates = generate_battery_candidates(
            n_candidates=self.n_candidates,
            base_params=self.base_params,
            seed=self.seed,
            prior_lessons=prior_lessons,
            experiment_memories=experiment_memories,
        )

        results: list[BatteryCandidateResult] = []

        for candidate in candidates:
            candidate.run_id = run_id
            cr = self._evaluate_candidate(candidate, baseline_metrics, run_id)
            results.append(cr)

        # Selective promotion policy
        scorable = [
            r for r in results
            if not r.evaluation.hard_fail and r.evaluation.final_score > 0
        ]
        scorable.sort(key=lambda r: r.evaluation.final_score, reverse=True)

        best = None
        alternate = None
        promoted_count = 0

        for r in scorable:
            passes_threshold = r.evaluation.final_score >= self.promotion_threshold
            # Stress gate: stress_resilience must be at least 0.4 to promote
            stress_ok = r.evaluation.score_components.get("stress_resilience", 1.0) >= 0.4

            if passes_threshold and stress_ok:
                if best is None:
                    best = r
                    r.decision = PromotionDecision.PROMOTED
                    r.candidate.status = CandidateStatus.PROMOTED
                    r.candidate.rejection_reason = ""
                    self.repo.save_domain_candidate(r.candidate)
                    promoted_count += 1
                    r.promotion_caveats = generate_candidate_caveats(
                        r.candidate, r.evaluation, baseline_metrics,
                        r.experiment_metrics, r.robustness_profile,
                    )
                elif (
                    alternate is None
                    and r.evaluation.final_score >= self.promotion_threshold - ALTERNATE_MARGIN
                    and r.candidate.rationale != best.candidate.rationale
                ):
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
                    r.decision = PromotionDecision.REJECTED
                    r.candidate.status = CandidateStatus.REJECTED
                    r.candidate.rejection_reason = generate_rejection_reason(
                        r.candidate, r.evaluation, self.promotion_threshold,
                        r.robustness_profile,
                    )
                    self.repo.save_domain_candidate(r.candidate)
            elif passes_threshold and not stress_ok:
                # Above threshold but stress-fragile — reject with explicit reason
                r.decision = PromotionDecision.REJECTED
                r.candidate.status = CandidateStatus.REJECTED
                stress_score = r.evaluation.score_components.get("stress_resilience", 0)
                r.candidate.rejection_reason = (
                    f"Score {r.evaluation.final_score:.4f} above threshold but "
                    f"stress_resilience {stress_score:.2f} below 0.40 minimum — "
                    "candidate is fragile under fast-charge or thermal stress"
                )
                self.repo.save_domain_candidate(r.candidate)

        return BatteryLoopResult(
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
    ) -> BatteryCandidateResult:
        """Evaluate a single candidate through the full pipeline."""

        # Physical plausibility check
        ok, reasons = check_physical_plausibility(candidate.parameters)
        if not ok:
            candidate.status = CandidateStatus.HARD_FAIL
            candidate.rejection_reason = "; ".join(reasons)
            self.repo.save_domain_candidate(candidate)
            eval_result = EvaluationResult(
                candidate_id=candidate.id,
                domain_name="battery_ecm",
                hard_fail=True,
                hard_fail_reasons=reasons,
            )
            self.repo.save_evaluation_result(eval_result)
            decision = PromotionDecision.REJECTED
            self._persist_memory(candidate, eval_result, decision, {})
            promo = PromotionRecord(
                candidate_id=candidate.id, domain_name="battery_ecm",
                decision=decision, evaluation_id=eval_result.id,
                reason=candidate.rejection_reason,
            )
            self.repo.save_promotion_record(promo)
            return BatteryCandidateResult(
                candidate=candidate, evaluation=eval_result,
                decision=decision, experiment_metrics={},
            )

        # Run baseline cycle experiment
        candidate.status = CandidateStatus.RUNNING
        self.repo.save_domain_candidate(candidate)

        cycle_result = run_experiment("baseline_cycle", candidate.parameters)
        cycle_result.candidate_id = candidate.id
        self.repo.save_experiment_result(cycle_result)

        if not cycle_result.success:
            candidate.status = CandidateStatus.HARD_FAIL
            candidate.rejection_reason = f"Baseline cycle failed: {cycle_result.error_message}"
            self.repo.save_domain_candidate(candidate)
            eval_result = EvaluationResult(
                candidate_id=candidate.id, domain_name="battery_ecm",
                hard_fail=True, hard_fail_reasons=[candidate.rejection_reason],
            )
            self.repo.save_evaluation_result(eval_result)
            decision = PromotionDecision.REJECTED
            self._persist_memory(candidate, eval_result, decision, {})
            promo = PromotionRecord(
                candidate_id=candidate.id, domain_name="battery_ecm",
                decision=decision, evaluation_id=eval_result.id,
                reason=candidate.rejection_reason,
            )
            self.repo.save_promotion_record(promo)
            return BatteryCandidateResult(
                candidate=candidate, evaluation=eval_result,
                decision=decision, experiment_metrics={},
            )

        # Run robustness profile (aging + C-rate + thermal)
        robustness = compute_robustness_profile(candidate.parameters, baseline_metrics)

        # Score
        eval_result = score_battery_candidate(
            cycle_result.metrics, baseline_metrics,
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
            candidate.rejection_reason = generate_rejection_reason(
                candidate, eval_result, self.promotion_threshold, robustness,
            )

        self.repo.save_domain_candidate(candidate)

        promo = PromotionRecord(
            candidate_id=candidate.id,
            domain_name="battery_ecm",
            decision=decision,
            evaluation_id=eval_result.id,
            reason=candidate.rejection_reason if decision == PromotionDecision.REJECTED else "Score above threshold",
            baseline_score=baseline_metrics.get("discharge_capacity", 0),
            candidate_score=cycle_result.metrics.get("discharge_capacity", 0),
        )
        self.repo.save_promotion_record(promo)

        self._persist_memory(
            candidate, eval_result, decision, cycle_result.metrics, robustness,
        )

        return BatteryCandidateResult(
            candidate=candidate,
            evaluation=eval_result,
            decision=decision,
            experiment_metrics=cycle_result.metrics,
            robustness_profile=robustness,
        )

    def _persist_memory(
        self,
        candidate: CandidateSpec,
        evaluation: EvaluationResult,
        decision: PromotionDecision,
        metrics: dict,
        robustness_profile: Optional[dict] = None,
    ) -> None:
        """Persist idea memory and experiment memory with stress data.

        Memory entries include:
        - Outcome and lesson (strongest/weakest component)
        - Stress fragility indicators from robustness profile
        - Weakness detection: low CE, low capacity, or stress fragility
        """
        components = evaluation.score_components or {}

        if evaluation.hard_fail:
            lesson = f"Hard fail: {'; '.join(evaluation.hard_fail_reasons)}"
        elif decision == PromotionDecision.PROMOTED:
            best_component = max(components, key=components.get) if components else "unknown"
            lesson = f"Promoted with score {evaluation.final_score:.4f}. Strongest component: {best_component}"
        else:
            worst_component = min(components, key=components.get) if components else "unknown"
            lesson = f"Rejected (score {evaluation.final_score:.4f}). Weakest component: {worst_component}"

        # Add stress summary to lesson if available
        if robustness_profile:
            wsr = robustness_profile.get("worst_stress_retention", 100)
            fc_fade = robustness_profile.get("fast_charge_fade_rate", 0)
            ts_fade = robustness_profile.get("thermal_stress_fade_rate", 0)
            if wsr < 90:
                lesson += f". Stress-fragile: worst retention {wsr:.1f}%"
            if fc_fade > 0.05:
                lesson += f". Fast-charge fade: {fc_fade:.3f}%/cycle"

        family = ""
        for fam_def in CANDIDATE_FAMILIES:
            if fam_def["family"] in candidate.title:
                family = fam_def["family"]
                break

        idea = IdeaMemoryEntry(
            domain_name="battery_ecm",
            candidate_id=candidate.id,
            candidate_title=candidate.title,
            candidate_family=family,
            rationale=candidate.rationale,
            outcome=decision.value,
            lesson=lesson,
            tags=list(candidate.parameters.keys()) if candidate.parameters else [],
        )
        self.repo.save_idea_memory(idea)

        informative_metrics = []
        weakness = ""
        if metrics:
            informative_metrics = [
                "discharge_capacity", "coulombic_efficiency", "internal_resistance",
            ]
            cap = metrics.get("discharge_capacity", 0)
            coul = metrics.get("coulombic_efficiency", 0)
            if coul < 98.0:
                weakness = f"Low coulombic efficiency: {coul:.2f}%"
            elif cap < 2.5:
                weakness = f"Low discharge capacity: {cap:.3f} Ah"

        # Stress-informed weakness detection
        if robustness_profile and not weakness:
            wsr = robustness_profile.get("worst_stress_retention", 100)
            if wsr < 85:
                weakness = f"Stress-fragile: worst retention {wsr:.1f}% under stress"

        template_name = "baseline_cycle+cycle_aging+crate_sweep+fast_charge_stress+thermal_stress_aging"

        exp_mem = ExperimentMemoryEntry(
            domain_name="battery_ecm",
            candidate_id=candidate.id,
            template_name=template_name,
            informative_metrics=informative_metrics,
            weakness_exposed=weakness,
            runtime_seconds=0.0,
            reproducibility_score=1.0,
        )
        self.repo.save_experiment_memory(exp_mem)


# ---------------------------------------------------------------------------
# Battery Benchmark mode
# ---------------------------------------------------------------------------

REFERENCE_CELL_PARAMS = {
    "capacity_ah": 3.2,
    "R0_mohm": 25.0,
    "R1_mohm": 12.0,
    "C1_F": 600.0,
    "v_min": 2.5,
    "v_max": 4.2,
    "coulombic_eff": 0.997,
    "fade_rate_per_cycle": 0.0003,
    "temp_coeff_r0": 0.003,
    "ocv_coeffs": [3.0, 1.5, -1.2, 0.85],
    "reference_name": "benchmark_nmc_21700_3200mah",
}


def run_battery_benchmark(
    repo: Repository,
    n_candidates: int = 6,
    seed: int = 42,
    promotion_threshold: float = 0.55,
) -> dict:
    """Run battery benchmark: full loop + held-out realism check."""
    loop = BatteryOptimizationLoop(
        repo, n_candidates=n_candidates,
        promotion_threshold=promotion_threshold, seed=seed,
    )
    result = loop.run(run_id=f"benchmark_{seed}")
    baseline = result.baseline_metrics

    # Held-out realism check
    ref_result = run_experiment("baseline_cycle", REFERENCE_CELL_PARAMS)
    ref_metrics = ref_result.metrics

    reference_comparison: dict = {
        "reference_name": REFERENCE_CELL_PARAMS["reference_name"],
        "reference_metrics": ref_metrics,
    }

    if result.best_promoted:
        bp = result.best_promoted
        ref_cap = ref_metrics.get("discharge_capacity", 0)
        cand_cap = bp.experiment_metrics.get("discharge_capacity", 0)
        if ref_cap > 0:
            reference_comparison["capacity_vs_reference"] = round(
                (cand_cap - ref_cap) / ref_cap, 4
            )
        ref_r = ref_metrics.get("internal_resistance", 0)
        cand_r = bp.experiment_metrics.get("internal_resistance", 0)
        if ref_r > 0:
            reference_comparison["resistance_vs_reference"] = round(
                (cand_r - ref_r) / ref_r, 4
            )
        reference_comparison["within_reference_envelope"] = (
            abs(reference_comparison.get("capacity_vs_reference", 0)) < 0.50
            and abs(reference_comparison.get("resistance_vs_reference", 0)) < 0.50
        )

    report: dict = {
        "benchmark_domain": "battery_ecm",
        "seed": seed,
        "baseline_candidate": {
            "params": "DEFAULT_CELL_PARAMS",
            "baseline_metrics": baseline,
        },
        "best_candidate": None,
        "robustness_profile": None,
        "caveats": [],
        "promotion_decision": "none",
        "reference_comparison": reference_comparison,
        "summary": result.summary(),
    }

    if result.best_promoted:
        bp = result.best_promoted
        report["best_candidate"] = {
            "title": bp.candidate.title,
            "score": bp.evaluation.final_score,
            "metrics": bp.experiment_metrics,
            "family": bp.candidate.title.split("variant")[0].replace("Battery ", "").strip(),
        }
        report["robustness_profile"] = {
            k: v for k, v in bp.robustness_profile.items() if k != "sweep_data"
        }
        report["caveats"] = bp.promotion_caveats
        report["promotion_decision"] = "promoted"

    return report
