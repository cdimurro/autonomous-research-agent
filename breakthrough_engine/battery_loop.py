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
# Sources: typical 18650/21700 cell datasheet ranges.
#   capacity_ah:          1.5–6.0 Ah   (18650: 2–3.5, 21700: 4–5)
#   R0_mohm:              10–100 mOhm  (fresh: 15–40, aged: 50–100)
#   R1_mohm:              5–80 mOhm    (fresh: 10–25, aged: 30–80)
#   C1_F:                 100–2000 F   (typical: 300–800)
#   coulombic_eff:        0.95–0.999   (good cell: 0.995+)
#   fade_rate_per_cycle:  0.0001–0.005 (0.01–0.5% per cycle)
PARAM_RANGES = {
    "capacity_ah": (1.5, 6.0),
    "R0_mohm": (10.0, 100.0),
    "R1_mohm": (5.0, 80.0),
    "C1_F": (100.0, 2000.0),
    "coulombic_eff": (0.95, 0.999),
    "fade_rate_per_cycle": (0.0001, 0.005),
}

# Candidate families with physically-grounded perturbation bounds.
CANDIDATE_FAMILIES = [
    {
        "family": "reduced_resistance",
        "rationale": "Lower R0/R1 via improved electrolyte or electrode contacts "
                     "reduces ohmic losses, improving energy efficiency and rate capability",
        "perturbations": {"R0_mohm": (-12.0, -3.0), "R1_mohm": (-8.0, -2.0)},
    },
    {
        "family": "improved_capacity",
        "rationale": "Higher capacity via thicker electrodes or better active material "
                     "utilization increases energy density",
        "perturbations": {"capacity_ah": (0.1, 0.5)},
    },
    {
        "family": "reduced_fade",
        "rationale": "Lower fade rate via improved SEI stability or electrolyte "
                     "additives extends cycle life",
        "perturbations": {"fade_rate_per_cycle": (-0.0003, -0.0001)},
    },
    {
        "family": "improved_efficiency",
        "rationale": "Higher coulombic efficiency via reduced side reactions "
                     "improves round-trip energy throughput",
        "perturbations": {"coulombic_eff": (0.001, 0.004)},
    },
    {
        "family": "combined_moderate",
        "rationale": "Co-optimized resistance reduction and fade improvement "
                     "reflecting realistic multi-step cell design improvement",
        "perturbations": {"R0_mohm": (-8.0, -2.0), "fade_rate_per_cycle": (-0.0002, -0.00005)},
    },
    {
        "family": "bounded_aggressive",
        "rationale": "Near-limit optimization across R0, capacity, and fade — "
                     "physically possible but represents best-in-class manufacturing",
        "perturbations": {
            "R0_mohm": (-15.0, -8.0),
            "capacity_ah": (0.2, 0.8),
            "fade_rate_per_cycle": (-0.0003, -0.0001),
        },
    },
]


def _check_cross_parameter_plausibility(params: dict) -> tuple[bool, list[str]]:
    """Reject unrealistic parameter *combinations* at generation time."""
    reasons: list[str] = []

    # Very low resistance with very high fade is contradictory:
    # low-resistance cells typically have stable interfaces
    r0 = params.get("R0_mohm", 30.0)
    fade = params.get("fade_rate_per_cycle", 0.0005)
    if r0 < 15.0 and fade > 0.003:
        reasons.append(
            f"Contradictory: low R0 ({r0:.1f} mOhm) with high fade ({fade*100:.2f}%/cycle) — "
            "low-resistance cells typically have stable interfaces"
        )

    # Very high capacity with very low coulombic efficiency is contradictory:
    # high-capacity cells need high efficiency to avoid thermal runaway
    cap = params.get("capacity_ah", 3.0)
    coul = params.get("coulombic_eff", 0.995)
    if cap > 5.0 and coul < 0.97:
        reasons.append(
            f"Contradictory: high capacity ({cap:.1f} Ah) with low coulombic efficiency "
            f"({coul*100:.1f}%) — high-capacity cells need high efficiency for thermal safety"
        )

    # Very high capacity with very low resistance is aspirational but
    # not contradictory — thick electrodes can still have good contacts
    # (so we don't reject this combination)

    return len(reasons) == 0, reasons


# Proposal rationale tags
PROPOSAL_TAG_MEMORY = "memory-supported"
PROPOSAL_TAG_EXPLORATORY = "exploratory"
PROPOSAL_TAG_RECOVERY = "recovery"
PROPOSAL_TAG_RETRY = "retry-with-correction"


def _compute_family_weights(
    prior_lessons: Optional[list[dict]],
    experiment_memories: Optional[list[dict]] = None,
) -> tuple[dict[str, float], dict[str, str]]:
    """Compute per-family selection weights from memory."""
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

    return weights, tags


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
    "capacity_retention": 0.20,
    "coulombic_improvement": 0.15,
    "resistance_improvement": 0.15,
    "fade_improvement": 0.15,
    "rate_capability": 0.10,
    "robustness": 0.10,
    "plausibility_penalty": 0.15,
}


def compute_robustness_profile(
    cell_params: dict,
    baseline_metrics: dict,
) -> dict:
    """Run multi-template stress evaluation and compute robustness indicators."""
    base_cap = baseline_metrics.get("discharge_capacity", 1)

    # C-rate sweep
    crate_result = run_experiment("crate_sweep", cell_params)
    crate_data = crate_result.raw_data.get("cycle_results", [])

    # Thermal sensitivity
    thermal_result = run_experiment("thermal_sensitivity", cell_params)
    thermal_data = thermal_result.raw_data.get("cycle_results", [])

    # Cycle aging
    aging_result = run_experiment("cycle_aging", cell_params)

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

    return {
        "worst_case_capacity_delta": round(worst_delta, 4),
        "crate_sensitivity": round(crate_sensitivity, 4),
        "thermal_sensitivity": round(thermal_sensitivity, 4),
        "capacity_retention": aging_result.metrics.get("capacity_retention", 100.0),
        "fade_rate": aging_result.metrics.get("fade_rate", 0.0),
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
    """Generate explicit caveats for a promoted or alternate candidate."""
    caveats: list[str] = list(evaluation.caveats)

    # What changed
    changed_params = []
    base = DEFAULT_CELL_PARAMS
    for param in ("R0_mohm", "R1_mohm", "capacity_ah", "coulombic_eff", "fade_rate_per_cycle", "C1_F"):
        base_val = base.get(param, 0)
        cand_val = candidate.parameters.get(param, base_val)
        if base_val and abs(cand_val - base_val) / max(abs(base_val), 1e-15) > 0.01:
            changed_params.append(f"{param}: {base_val} → {cand_val:.4g}")
    if changed_params:
        caveats.append(f"Parameter changes: {'; '.join(changed_params)}")

    # Score concentration
    components = evaluation.score_components
    if components:
        strongest = max(components, key=lambda k: components[k])
        weakest = min(components, key=lambda k: components[k])
        if components[strongest] > 0.7:
            caveats.append(f"Gain concentrated in {strongest} (score={components[strongest]:.2f})")
        if components[weakest] < 0.3:
            caveats.append(f"Weakness in {weakest} (score={components[weakest]:.2f})")

    # Degradation warnings
    base_cap = baseline_metrics.get("discharge_capacity", 0)
    cand_cap = candidate_metrics.get("discharge_capacity", 0)
    if base_cap > 0 and cand_cap < base_cap * 0.95:
        caveats.append(f"Capacity decreased: {cand_cap:.3f} Ah vs baseline {base_cap:.3f} Ah")

    base_coul = baseline_metrics.get("coulombic_efficiency", 0)
    cand_coul = candidate_metrics.get("coulombic_efficiency", 0)
    if base_coul > 0 and cand_coul < base_coul - 0.5:
        caveats.append(f"Coulombic efficiency decreased: {cand_coul:.2f}% vs baseline {base_coul:.2f}%")

    return caveats


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
            if r.evaluation.final_score >= self.promotion_threshold:
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
                    r.candidate.rejection_reason = (
                        f"Score {r.evaluation.final_score:.4f} above threshold "
                        f"but not selected (selective promotion)"
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
            candidate.rejection_reason = f"Score {eval_result.final_score:.4f} below threshold {self.promotion_threshold}"

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

        self._persist_memory(candidate, eval_result, decision, cycle_result.metrics)

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
    ) -> None:
        """Persist idea memory and experiment memory."""
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
            informative_metrics = ["discharge_capacity", "coulombic_efficiency", "internal_resistance"]
            cap = metrics.get("discharge_capacity", 0)
            coul = metrics.get("coulombic_efficiency", 0)
            if coul < 98.0:
                weakness = f"Low coulombic efficiency: {coul:.2f}%"
            elif cap < 2.5:
                weakness = f"Low discharge capacity: {cap:.3f} Ah"

        exp_mem = ExperimentMemoryEntry(
            domain_name="battery_ecm",
            candidate_id=candidate.id,
            template_name="baseline_cycle+cycle_aging+crate_sweep",
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
