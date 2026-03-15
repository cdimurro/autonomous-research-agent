"""PV optimization loop — end-to-end candidate generation, experiment,
scoring, and promotion for PV I-V characterization.

This is the first narrow-domain optimization loop. It:
1. Generates PV candidate parameter variations
2. Runs fixed experiments (STC, sweeps) via pvlib
3. Scores candidates against a baseline
4. Applies hard-fail gates
5. Promotes or rejects with reason
6. Persists idea memory and experiment memory
"""

from __future__ import annotations

import logging
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
# Candidate generation
# ---------------------------------------------------------------------------

# Parameter perturbation ranges (physically plausible bounds)
PARAM_RANGES = {
    "I_L_ref": (5.0, 15.0),       # A — photocurrent
    "I_o_ref": (1e-13, 1e-7),     # A — saturation current (log scale)
    "R_s": (0.05, 3.0),           # ohm — series resistance
    "R_sh_ref": (50.0, 2000.0),   # ohm — shunt resistance
    "a_ref": (0.8, 3.0),          # V — ideality factor
    "alpha_sc": (0.0005, 0.01),   # A/C — temp coeff of Isc
}

# Candidate families with rationale
CANDIDATE_FAMILIES = [
    {
        "family": "reduced_series_resistance",
        "rationale": "Lower Rs improves fill factor and Pmax by reducing ohmic losses",
        "perturbations": {"R_s": (-0.5, -0.1)},  # delta from default
    },
    {
        "family": "improved_junction_quality",
        "rationale": "Lower I_o improves Voc by reducing recombination current",
        "perturbations": {"I_o_ref": (0.01, 0.5)},  # multiplier on default
    },
    {
        "family": "enhanced_photocurrent",
        "rationale": "Higher I_L increases Isc and Pmax through better light absorption",
        "perturbations": {"I_L_ref": (0.5, 3.0)},  # delta from default
    },
    {
        "family": "improved_shunt_resistance",
        "rationale": "Higher Rsh reduces leakage current, improving Voc and FF",
        "perturbations": {"R_sh_ref": (100.0, 600.0)},  # delta from default
    },
    {
        "family": "combined_improvement",
        "rationale": "Simultaneous improvement in Rs and Rsh for better overall performance",
        "perturbations": {"R_s": (-0.3, -0.05), "R_sh_ref": (50.0, 300.0)},
    },
    {
        "family": "aggressive_optimization",
        "rationale": "Push multiple parameters toward theoretical limits",
        "perturbations": {"R_s": (-0.4, -0.2), "I_o_ref": (0.01, 0.1), "R_sh_ref": (200.0, 800.0)},
    },
]


def generate_pv_candidates(
    n_candidates: int = 6,
    base_params: Optional[dict] = None,
    seed: Optional[int] = None,
    prior_lessons: Optional[list[dict]] = None,
) -> list[CandidateSpec]:
    """Generate PV candidate parameter variations.

    Uses physically-informed perturbation families to propose candidates.
    Avoids families that have been tried and failed (via prior_lessons).
    """
    if seed is not None:
        random.seed(seed)

    base = dict(base_params or DEFAULT_CELL_PARAMS)
    candidates = []

    # Filter out families that have consistently failed
    failed_families = set()
    if prior_lessons:
        family_outcomes: dict[str, list[str]] = {}
        for lesson in prior_lessons:
            fam = lesson.get("candidate_family", "")
            outcome = lesson.get("outcome", "")
            if fam:
                family_outcomes.setdefault(fam, []).append(outcome)
        for fam, outcomes in family_outcomes.items():
            # Skip family if all prior attempts were rejected/hard_fail
            if outcomes and all(o in ("rejected", "hard_fail") for o in outcomes):
                failed_families.add(fam)
                logger.info("Skipping family %s: all prior attempts failed", fam)

    available_families = [f for f in CANDIDATE_FAMILIES if f["family"] not in failed_families]
    if not available_families:
        available_families = CANDIDATE_FAMILIES  # fallback: use all

    for i in range(n_candidates):
        family = available_families[i % len(available_families)]
        params = dict(base)
        description_parts = []

        for param, delta_range in family["perturbations"].items():
            if param == "I_o_ref":
                # Multiplicative perturbation for I_o (log scale)
                multiplier = random.uniform(delta_range[0], delta_range[1])
                params[param] = base.get(param, 1e-10) * multiplier
                description_parts.append(f"{param}*={multiplier:.3f}")
            else:
                delta = random.uniform(delta_range[0], delta_range[1])
                params[param] = base.get(param, 0) + delta
                description_parts.append(f"{param}+={delta:.4f}")

        # Clamp to physical bounds
        for param, (lo, hi) in PARAM_RANGES.items():
            if param in params:
                params[param] = max(lo, min(hi, params[param]))

        candidate = CandidateSpec(
            domain_name="pv_iv",
            title=f"PV {family['family']} variant {i+1}",
            description=", ".join(description_parts),
            parameters=params,
            rationale=family["rationale"],
            source="perturbation",
        )
        candidates.append(candidate)

    return candidates


# ---------------------------------------------------------------------------
# PV Scoring
# ---------------------------------------------------------------------------

PV_SCORE_WEIGHTS = {
    "pmax_improvement": 0.30,
    "ff_improvement": 0.20,
    "efficiency_improvement": 0.20,
    "robustness": 0.15,
    "plausibility_penalty": 0.15,
}


def score_pv_candidate(
    candidate_metrics: dict,
    baseline_metrics: dict,
    sweep_results: Optional[list[dict]] = None,
) -> EvaluationResult:
    """Score a PV candidate against baseline metrics.

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
        # Sigmoid-like mapping: 0 at no improvement, 1 at +20% improvement
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

    # --- Robustness (from sweep data) ---
    if sweep_results and len(sweep_results) > 1:
        pmaxes = [s.get("Pmax", 0) for s in sweep_results if s.get("Pmax", 0) > 0]
        if pmaxes:
            mean_pmax = sum(pmaxes) / len(pmaxes)
            variance = sum((p - mean_pmax) ** 2 for p in pmaxes) / len(pmaxes)
            cv = (variance ** 0.5) / mean_pmax if mean_pmax > 0 else 1.0
            # Lower CV = more robust = higher score
            components["robustness"] = max(0.0, min(1.0, 1.0 - cv * 2))
        else:
            components["robustness"] = 0.0
    else:
        components["robustness"] = 0.5  # neutral if no sweep data

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
# Full PV optimization loop
# ---------------------------------------------------------------------------

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
        # Load prior lessons
        prior_lessons = self.repo.list_idea_memory("pv_iv", limit=50)

        # 1. Generate baseline
        logger.info("Running baseline experiment...")
        baseline_result = run_experiment("stc_baseline", self.base_params)
        baseline_metrics = baseline_result.metrics

        # 2. Generate candidates
        logger.info("Generating %d PV candidates...", self.n_candidates)
        candidates = generate_pv_candidates(
            n_candidates=self.n_candidates,
            base_params=self.base_params,
            seed=self.seed,
            prior_lessons=prior_lessons,
        )

        results: list[PVCandidateResult] = []
        promoted_count = 0

        for candidate in candidates:
            candidate.run_id = run_id
            cr = self._evaluate_candidate(candidate, baseline_metrics, run_id)
            results.append(cr)
            if cr.decision == PromotionDecision.PROMOTED:
                promoted_count += 1

        # Select best promoted candidate (one promotion per run)
        best = None
        if promoted_count > 0:
            promoted = [r for r in results if r.decision == PromotionDecision.PROMOTED]
            best = max(promoted, key=lambda r: r.evaluation.final_score)

        return PVLoopResult(
            run_id=run_id,
            baseline_metrics=baseline_metrics,
            candidates=results,
            best_promoted=best,
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

        # Run temperature sweep for robustness data
        temp_result = run_experiment("temperature_sweep", candidate.parameters)
        temp_result.candidate_id = candidate.id
        self.repo.save_experiment_result(temp_result)
        sweep_data = temp_result.raw_data.get("sweep_results", [])

        # Score
        eval_result = score_pv_candidate(
            stc_result.metrics, baseline_metrics, sweep_data,
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
    ):
        self.candidate = candidate
        self.evaluation = evaluation
        self.decision = decision
        self.experiment_metrics = experiment_metrics
        self.sweep_data = sweep_data


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
    ):
        self.run_id = run_id
        self.baseline_metrics = baseline_metrics
        self.candidates = candidates
        self.best_promoted = best_promoted
        self.total_candidates = total_candidates
        self.promoted_count = promoted_count
        self.rejected_count = rejected_count
        self.hard_fail_count = hard_fail_count

    def summary(self) -> dict:
        """Return a summary dict suitable for logging/persistence."""
        return {
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
