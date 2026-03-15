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
