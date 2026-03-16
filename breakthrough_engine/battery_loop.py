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
from .battery_sidecar import (
    CONCORDANCE_CONFIRM_THRESHOLD,
    CONCORDANCE_VETO_THRESHOLD,
    PyBaMMSidecarResult,
    SidecarStatus,
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
#   R0_mohm:              14–70 mOhm   (fresh: 15–40, aged: 50–70)
#                         Floor raised: sub-14 requires tab-less or prismatic
#                         Cap tightened from 80: >70 is deep-EOL
#   R1_mohm:              6–45 mOhm    (fresh: 8–20, aged: 25–45)
#                         Tightened both ends for realistic charge-transfer
#   C1_F:                 250–1200 F   (typical: 300–800)
#                         Tightened: sub-250 implies unrealistic fast dynamics;
#                         >1200 implies excessive double-layer contribution
#   coulombic_eff:        0.975–0.9995 (good cell: 0.995+, best: 0.9995)
#                         Floor raised from 0.97: sub-97.5% indicates
#                         significant parasitic losses incompatible with
#                         modern NMC cells
#   fade_rate_per_cycle:  0.0001–0.0025 (0.01–0.25% per cycle)
#                         Cap lowered from 0.003: >0.25%/cycle implies
#                         severe degradation (lithium plating or
#                         electrolyte decomposition)
#   temp_coeff_r0:        0.001–0.008 (per degC from 25C)
#                         Added: bounds on realistic temperature sensitivity
PARAM_RANGES = {
    "capacity_ah": (2.0, 5.5),
    "R0_mohm": (14.0, 70.0),
    "R1_mohm": (6.0, 45.0),
    "C1_F": (250.0, 1200.0),
    "coulombic_eff": (0.975, 0.9995),
    "fade_rate_per_cycle": (0.0001, 0.0025),
    "temp_coeff_r0": (0.001, 0.008),
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
        "temp_coeff_r0": 0.003,
        "notes": "Baseline NMC 18650, balanced performance",
    },
    {
        "name": "Samsung_50E_21700",
        "capacity_ah": 5.0, "R0_mohm": 35.0, "R1_mohm": 18.0,
        "coulombic_eff": 0.996, "fade_rate_per_cycle": 0.0004,
        "temp_coeff_r0": 0.004,
        "notes": "High-capacity 21700, moderate resistance",
    },
    {
        "name": "Samsung_30Q_18650",
        "capacity_ah": 3.0, "R0_mohm": 22.0, "R1_mohm": 12.0,
        "coulombic_eff": 0.997, "fade_rate_per_cycle": 0.0003,
        "temp_coeff_r0": 0.003,
        "notes": "Low-resistance NMC 18650, good rate capability",
    },
    {
        "name": "LG_MJ1_18650",
        "capacity_ah": 3.5, "R0_mohm": 40.0, "R1_mohm": 20.0,
        "coulombic_eff": 0.994, "fade_rate_per_cycle": 0.0006,
        "temp_coeff_r0": 0.004,
        "notes": "High-capacity 18650, trades resistance for capacity",
    },
    {
        "name": "Molicel_P42A_21700",
        "capacity_ah": 4.2, "R0_mohm": 18.0, "R1_mohm": 10.0,
        "coulombic_eff": 0.996, "fade_rate_per_cycle": 0.0005,
        "temp_coeff_r0": 0.003,
        "notes": "High-power 21700, fast-charge capable, low impedance",
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
                     "Bounded: 3–8 mOhm R0 reduction is achievable via "
                     "electrolyte optimization (e.g., LiPF6 concentration tuning)",
        "perturbations": {"R0_mohm": (-8.0, -3.0), "R1_mohm": (-5.0, -1.5)},
        "tradeoff_risk": "Lower R0 may indicate thinner separator → safety concern; "
                         "fast-charge fade may worsen if heat dissipation changes",
    },
    {
        "family": "improved_capacity",
        "rationale": "Higher capacity via silicon-graphite blended anode or "
                     "higher Ni-content cathode increases energy density. "
                     "Bounded: 0.1–0.35 Ah gain is realistic for incremental "
                     "active material improvements",
        "perturbations": {
            "capacity_ah": (0.1, 0.35),
            "fade_rate_per_cycle": (0.00002, 0.00008),
        },
        "tradeoff_risk": "Higher capacity often trades cycle life (higher Ni = faster fade); "
                         "thicker electrodes degrade rate capability under fast-charge",
    },
    {
        "family": "reduced_fade",
        "rationale": "Lower fade rate via electrolyte additives (FEC, VC) or "
                     "atomic layer deposition coatings improves SEI stability. "
                     "Bounded: 0.01–0.02%/cycle reduction is realistic",
        "perturbations": {
            "fade_rate_per_cycle": (-0.0002, -0.0001),
            "R1_mohm": (0.5, 2.0),
        },
        "tradeoff_risk": "Additives may increase impedance or reduce rate capability; "
                         "surface coatings add charge-transfer resistance",
    },
    {
        "family": "improved_efficiency",
        "rationale": "Higher coulombic efficiency via reduced parasitic reactions "
                     "(improved electrolyte purity, surface coatings). "
                     "Bounded: 0.1–0.25% improvement is realistic",
        "perturbations": {"coulombic_eff": (0.001, 0.0025)},
        "tradeoff_risk": "Marginal CE gains may not survive high-temperature operation; "
                         "gains observed at 25C may vanish at elevated temperatures",
    },
    {
        "family": "combined_moderate",
        "rationale": "Co-optimized resistance reduction and fade improvement "
                     "reflecting a multi-lever cell redesign (electrolyte + coating). "
                     "Each lever kept conservative: R0 -2 to -5 mOhm, fade -0.005 to -0.015%/cycle",
        "perturbations": {"R0_mohm": (-5.0, -2.0), "fade_rate_per_cycle": (-0.00015, -0.00005)},
        "tradeoff_risk": "Multi-lever changes harder to attribute; interaction effects possible; "
                         "combined benefit may not survive fast-charge stress",
    },
    {
        "family": "rate_optimized",
        "rationale": "Optimized for fast-charge capability via lower R0 and R1 "
                     "with modest capacity tradeoff. Targets Molicel P42A-class "
                     "impedance profile suited for 2C+ charge rates",
        "perturbations": {
            "R0_mohm": (-10.0, -5.0),
            "R1_mohm": (-6.0, -3.0),
            "capacity_ah": (-0.15, 0.05),
            "temp_coeff_r0": (-0.001, 0.0),
        },
        "tradeoff_risk": "Low-impedance design may sacrifice energy density; "
                         "thermal management becomes critical at high rates; "
                         "capacity tradeoff may not justify rate improvement",
    },
    {
        "family": "bounded_aggressive",
        "rationale": "Near-best-in-class across R0, capacity, and fade — "
                     "represents what the best commercial cells achieve. "
                     "Bounded: P42A-class resistance + modest capacity gain + good fade",
        "perturbations": {
            "R0_mohm": (-10.0, -5.0),
            "capacity_ah": (0.15, 0.4),
            "fade_rate_per_cycle": (-0.00015, -0.00005),
        },
        "tradeoff_risk": "Simultaneously achieving all three is rare; likely requires "
                         "advanced manufacturing (tab-less + high-Ni + premium electrolyte); "
                         "fast-charge stress performance unverified",
    },
    # ── Cathode-focused candidate families ───────────────────────────────
    # These use chemistry-specific base params from CATHODE_ECM_PROFILES
    # instead of DEFAULT_CELL_PARAMS, then apply perturbations on top.
    {
        "family": "cathode_high_ni",
        "rationale": "NMC-811/NCA cathode with high Ni content for increased "
                     "energy density. Higher capacity but faster degradation, "
                     "especially under fast-charge and thermal stress. "
                     "Grounded in Noh et al. 2013 + PyBaMM Chen2020",
        "perturbations": {
            "capacity_ah": (0.3, 0.5),
            "fade_rate_per_cycle": (0.0002, 0.0004),
            "R0_mohm": (-8.0, -3.0),
        },
        "tradeoff_risk": "High-Ni cathodes suffer from structural transformation "
                         "and oxygen release at high temperature; fast-charge "
                         "accelerates degradation; thermal runaway risk increases",
        "chemistry": "NMC_811",
    },
    {
        "family": "cathode_lfp",
        "rationale": "LFP cathode with superior cycle life and thermal stability "
                     "but lower energy density and higher impedance. "
                     "Grounded in PyBaMM Prada2013 + A123 ANR26650 datasheet",
        "perturbations": {
            # CC-BE-2471: explore both resistance improvement and degradation
            # relative to LFP base (R0=42). Some candidates should demonstrate
            # R&D-grade impedance reduction achievable with electrolyte/coating work.
            "capacity_ah": (-0.3, 0.1),
            "fade_rate_per_cycle": (-0.0003, -0.0001),
            "R0_mohm": (-8.0, 6.0),
        },
        "tradeoff_risk": "LFP has inherently lower energy density; high impedance "
                         "limits fast-charge capability; poor rate capability at "
                         "low temperatures",
        "chemistry": "LFP",
    },
    {
        "family": "cathode_lmfp",
        "rationale": "LMFP (Mn-doped LFP) cathode bridging LFP and NMC: "
                     "higher voltage from Mn redox without Ni instability. "
                     "Based on CATL M3P press data; limited peer-reviewed data",
        "perturbations": {
            # CC-BE-2471: explore LMFP variants with improved impedance
            "capacity_ah": (-0.2, 0.1),
            "fade_rate_per_cycle": (-0.0002, -0.00005),
            "R0_mohm": (-6.0, 4.0),
        },
        "tradeoff_risk": "LMFP is less proven than LFP or NMC; Mn dissolution "
                         "may cause long-term fade; limited published cycling data",
        "chemistry": "LMFP",
    },
    {
        "family": "cathode_nmc532",
        "rationale": "NMC-532 cathode: conservative Ni content for better "
                     "cycle life than NMC-622/811 at modest capacity tradeoff. "
                     "Grounded in OKane2022 (PyBaMM) adapted for 532 stoichiometry",
        "perturbations": {
            # CC-BE-2471: explore NMC-532 variants including impedance improvements
            "capacity_ah": (-0.1, 0.1),
            "fade_rate_per_cycle": (-0.00015, -0.00005),
            "R0_mohm": (-5.0, 3.0),
        },
        "tradeoff_risk": "Lower energy density than high-Ni alternatives; "
                         "may not meet aggressive capacity targets; "
                         "resistance slightly higher than NMC-622",
        "chemistry": "NMC_532",
    },
]


# ---------------------------------------------------------------------------
# Cathode ECM profiles — chemistry-specific base parameters
# ---------------------------------------------------------------------------

CATHODE_ECM_PROFILES = {
    "NMC_811": {
        "base_params": {
            "capacity_ah": 3.5, "R0_mohm": 22.0, "R1_mohm": 11.0,
            "C1_F": 450.0, "coulombic_eff": 0.993,
            "fade_rate_per_cycle": 0.0008, "v_max": 4.25, "v_min": 2.5,
            "temp_coeff_r0": 0.004,
            "ocv_coeffs": [3.0, 1.6, -1.3, 0.9],
        },
        "profile_source": "Noh et al. 2013 + PyBaMM Chen2020 parameter set",
        "profile_confidence": "literature-backed",
        "pybamm_parameter_set": "Chen2020",
        "sidecar_note": "Live sidecar validation: concordance 0.62 (confirmed). "
                        "Capacity mismatch expected (ECM 3.5 vs DFN 5.07 — different cell sizes).",
    },
    "LFP": {
        "base_params": {
            "capacity_ah": 2.5, "R0_mohm": 42.0, "R1_mohm": 22.0,
            "C1_F": 800.0, "coulombic_eff": 0.999,
            "fade_rate_per_cycle": 0.00015, "v_max": 3.65, "v_min": 2.0,
            "temp_coeff_r0": 0.002,
            "ocv_coeffs": [2.5, 1.8, -1.5, 0.55],
        },
        "profile_source": "PyBaMM Prada2013 + A123 ANR26650 datasheet",
        "profile_confidence": "literature-backed",
        "pybamm_parameter_set": "Prada2013",
        "sidecar_note": "Live sidecar validation: concordance 0.67 (confirmed). "
                        "Best agreement of all chemistries — LFP capacity closely matches Prada2013.",
    },
    "LMFP": {
        "base_params": {
            "capacity_ah": 2.8, "R0_mohm": 35.0, "R1_mohm": 18.0,
            "C1_F": 650.0, "coulombic_eff": 0.998,
            "fade_rate_per_cycle": 0.0002, "v_max": 4.1, "v_min": 2.0,
            "temp_coeff_r0": 0.003,
            "ocv_coeffs": [2.8, 1.7, -1.4, 0.7],
        },
        "profile_source": "CATL M3P press releases, limited peer-reviewed data",
        "profile_confidence": "heuristic",
        "pybamm_parameter_set": None,  # no PyBaMM set → sidecar returns ERROR for LMFP
        "sidecar_note": "Live sidecar validation: ERROR (no PyBaMM parameter set). "
                        "LMFP candidates verified by ECM only.",
    },
    "NMC_532": {
        "base_params": {
            "capacity_ah": 2.9, "R0_mohm": 32.0, "R1_mohm": 14.0,
            "C1_F": 550.0, "coulombic_eff": 0.996,
            "fade_rate_per_cycle": 0.0003, "v_max": 4.2, "v_min": 2.5,
            "temp_coeff_r0": 0.003,
            "ocv_coeffs": [3.0, 1.5, -1.2, 0.85],
        },
        "profile_source": "OKane2022 (PyBaMM) adapted for 532 stoichiometry",
        "profile_confidence": "literature-backed",
        "pybamm_parameter_set": "OKane2022",
        "sidecar_note": "Live sidecar validation: concordance 0.58 (caveat range). "
                        "Capacity mismatch (ECM 2.9 vs DFN 5.02 — OKane2022 models a larger cell).",
    },
}


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

    # 7. Very low fade + very high R0 is suspicious:
    #    Low degradation with high impedance suggests the cell was only
    #    tested at very gentle conditions. Under fast-charge stress,
    #    high-R0 cells generate more heat → accelerated degradation.
    if fade < 0.00015 and r0 > 50.0:
        reasons.append(
            f"Suspicious: very low fade ({fade*100:.3f}%/cycle) with high R0 "
            f"({r0:.1f} mOhm) — low fade unlikely to survive fast-charge stress "
            "due to resistive heating"
        )

    # 8. Chemistry-aware: LFP-like impedance with NMC voltage range.
    #    LFP operates at 3.2-3.4V plateau; v_max > 3.8V with high R0
    #    and low capacity suggests LFP parameters with wrong voltage limits.
    v_max = params.get("v_max", 4.2)
    if cap < 2.8 and r0 > 35.0 and v_max > 3.8:
        reasons.append(
            f"Contradictory: LFP-like parameters (cap={cap:.1f}Ah, R0={r0:.1f}mOhm) "
            f"with NMC voltage range (v_max={v_max:.2f}V) — "
            "LFP cells operate below 3.65V"
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
        fast_charge_weak: dict[str, int] = {}
        resistance_growth_weak: dict[str, int] = {}
        for mem in experiment_memories:
            cid = mem.get("candidate_id", "")
            weakness = mem.get("weakness_exposed", "")
            if not weakness:
                continue
            # Map candidate back to family via idea memory
            fam = _candidate_id_to_family(cid, prior_lessons)
            if fam:
                weakness_counts[fam] = weakness_counts.get(fam, 0) + 1
                wl = weakness.lower()
                if "stress" in wl or "fragile" in wl:
                    stress_fragile[fam] = stress_fragile.get(fam, 0) + 1
                if "fast-charge" in wl or "fast_charge" in wl or "3c" in wl:
                    fast_charge_weak[fam] = fast_charge_weak.get(fam, 0) + 1
                if "resistance" in wl and "growth" in wl:
                    resistance_growth_weak[fam] = resistance_growth_weak.get(fam, 0) + 1

        # Cathode-specific weakness tracking
        cathode_thermal_weak: dict[str, int] = {}
        for mem in experiment_memories:
            cid = mem.get("candidate_id", "")
            weakness = mem.get("weakness_exposed", "")
            if not weakness:
                continue
            fam = _candidate_id_to_family(cid, prior_lessons)
            if fam:
                wl = weakness.lower()
                if "cathode" in wl or "thermal_instability" in wl or "thermal instability" in wl:
                    cathode_thermal_weak[fam] = cathode_thermal_weak.get(fam, 0) + 1

        for fam, count in weakness_counts.items():
            if fam in weights and count >= 2:
                # Repeated weakness → down-weight further
                weights[fam] *= 0.7
                if fam in stress_fragile and stress_fragile[fam] >= 2:
                    weights[fam] *= 0.5
                    tags[fam] = PROPOSAL_TAG_STRESS_INFORMED
                # Fast-charge-specific weakness: steer toward rate-optimized
                if fam in fast_charge_weak and fast_charge_weak[fam] >= 2:
                    weights[fam] *= 0.6
                    tags[fam] = PROPOSAL_TAG_STRESS_INFORMED
                # Resistance growth weakness: penalize families that
                # repeatedly show impedance rise
                if fam in resistance_growth_weak and resistance_growth_weak[fam] >= 2:
                    weights[fam] *= 0.6
                # Cathode-specific thermal instability
                if fam in cathode_thermal_weak and cathode_thermal_weak[fam] >= 2:
                    weights[fam] *= 0.6
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
    """Select n families using weighted sampling with diversity controls.

    CC-BE-2472: Ensures no single family appears more than MAX_FAMILY_REPEAT
    times per run, and at least MIN_DISTINCT families are represented.
    This prevents runs dominated by one family while still respecting
    memory-guided preferences.
    """
    # Scale repeat cap: for small n (6-8) cap at 2; for large n allow more
    MAX_FAMILY_REPEAT = max(2, n // len(families) + 1) if families else 2
    MIN_DISTINCT = min(3, n, len(families))

    available = list(families)
    w = [weights.get(f["family"], 1.0) for f in available]
    total_w = sum(w)
    if total_w <= 0:
        return [available[i % len(available)] for i in range(n)]

    selected = []
    family_counts: dict[str, int] = {}

    for _ in range(n):
        # Compute available weights (zero out maxed-out families)
        adj_w = []
        for idx, f in enumerate(available):
            fam = f["family"]
            if family_counts.get(fam, 0) >= MAX_FAMILY_REPEAT:
                adj_w.append(0.0)
            else:
                adj_w.append(w[idx])

        adj_total = sum(adj_w)
        if adj_total <= 0:
            # All families maxed — pick least-used
            for f in available:
                if f["family"] not in family_counts:
                    selected.append(f)
                    family_counts[f["family"]] = 1
                    break
            else:
                selected.append(rng.choice(available))
            continue

        r = rng.random() * adj_total
        cumulative = 0.0
        for idx, fw in enumerate(adj_w):
            cumulative += fw
            if r <= cumulative:
                chosen = available[idx]
                selected.append(chosen)
                family_counts[chosen["family"]] = family_counts.get(chosen["family"], 0) + 1
                break
        else:
            selected.append(available[-1])
            family_counts[available[-1]["family"]] = family_counts.get(available[-1]["family"], 0) + 1

    # Enforce MIN_DISTINCT: if too few families, swap last picks for under-represented ones
    distinct = len(set(s["family"] for s in selected))
    if distinct < MIN_DISTINCT and len(selected) >= MIN_DISTINCT:
        present = {s["family"] for s in selected}
        absent = [f for f in available if f["family"] not in present and w[available.index(f)] > 0]
        rng.shuffle(absent)
        # Replace duplicate entries from the end
        for replacement in absent:
            if distinct >= MIN_DISTINCT:
                break
            # Find last duplicate to replace
            for i in range(len(selected) - 1, -1, -1):
                fam = selected[i]["family"]
                if sum(1 for s in selected if s["family"] == fam) > 1:
                    selected[i] = replacement
                    distinct += 1
                    break

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
        # Chemistry-anchored generation: cathode families use chemistry-specific
        # base params instead of DEFAULT_CELL_PARAMS
        chemistry = family.get("chemistry")
        if chemistry and chemistry in CATHODE_ECM_PROFILES:
            profile = CATHODE_ECM_PROFILES[chemistry]
            params = dict(profile["base_params"])
            profile_confidence = profile.get("profile_confidence", "heuristic")
        else:
            params = dict(base)
            profile_confidence = None

        description_parts = []
        proposal_tag = family_tags.get(family["family"], PROPOSAL_TAG_EXPLORATORY)

        for param, delta_range in family["perturbations"].items():
            delta = rng.uniform(delta_range[0], delta_range[1])
            params[param] = params.get(param, base.get(param, 0)) + delta
            description_parts.append(f"{param}+={delta:.6f}")

        # Clamp to physical bounds
        for param, (lo, hi) in PARAM_RANGES.items():
            if param in params:
                params[param] = max(lo, min(hi, params[param]))

        # Cross-parameter plausibility filter
        cross_ok, cross_reasons = _check_cross_parameter_plausibility(params)
        if not cross_ok:
            # Regenerate with conservative perturbations from the same base
            if chemistry and chemistry in CATHODE_ECM_PROFILES:
                params = dict(CATHODE_ECM_PROFILES[chemistry]["base_params"])
            else:
                params = dict(base)
            description_parts = []
            for param, delta_range in family["perturbations"].items():
                mid = (delta_range[0] + delta_range[1]) / 2
                half_span = (delta_range[1] - delta_range[0]) / 4
                delta = rng.uniform(mid - half_span, mid + half_span)
                params[param] = params.get(param, base.get(param, 0)) + delta
                description_parts.append(f"{param}+={delta:.6f}(conservative)")
            for param, (lo, hi) in PARAM_RANGES.items():
                if param in params:
                    params[param] = max(lo, min(hi, params[param]))

        rationale = f"[{proposal_tag}] {family['rationale']}"
        if profile_confidence:
            rationale += f" [profile: {profile_confidence}]"

        candidate = CandidateSpec(
            domain_name="battery_ecm",
            title=f"Battery {family['family']} variant {i+1}",
            description=", ".join(description_parts),
            family=family["family"],
            parameters=params,
            rationale=rationale,
            source="perturbation",
        )
        candidates.append(candidate)

    return candidates


# ---------------------------------------------------------------------------
# Chemistry detection (CC-BE-2471)
# ---------------------------------------------------------------------------

# Map cathode family names to CATHODE_ECM_PROFILES keys
_FAMILY_TO_CHEMISTRY = {
    "cathode_high_ni": "NMC_811",
    "cathode_lfp": "LFP",
    "cathode_lmfp": "LMFP",
    "cathode_nmc532": "NMC_532",
}


def _candidate_chemistry_key(candidate: CandidateSpec) -> Optional[str]:
    """Return the CATHODE_ECM_PROFILES key for a cathode candidate, or None."""
    return _FAMILY_TO_CHEMISTRY.get(candidate.family)


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

    # Repeated fast-charge stress (CC-BE-2427): 3C for 30 cycles
    repeated_fc_result = run_experiment("repeated_fast_charge_stress", cell_params)

    # Thermal stress aging (CC-BE-2417)
    thermal_stress_result = run_experiment("thermal_stress_aging", cell_params)

    # Cathode thermal stability (2C/55C, 15 cycles)
    cathode_thermal_result = run_experiment("cathode_thermal_stability", cell_params)

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
            "repeated_fast_charge_retention": 100.0,
            "repeated_fast_charge_fade_rate": 0.0,
            "resistance_growth_pct": 0.0,
            "thermal_stress_fade_rate": 0.0,
            "thermal_stress_penalty_pct": 0.0,
            "cathode_thermal_retention": 100.0,
            "cathode_thermal_fade_rate": 0.0,
            "cathode_thermal_penalty_pct": 0.0,
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

    # Fast-charge stress metrics (2C, 20 cycles)
    fc_fade = fast_charge_result.metrics.get("stress_fade_rate", 0.0)
    fc_penalty = fast_charge_result.metrics.get("stress_penalty_pct", 0.0)
    fc_retention = fast_charge_result.metrics.get("capacity_retention", 100.0)

    # Repeated fast-charge stress metrics (3C, 30 cycles)
    rfc_retention = repeated_fc_result.metrics.get("fast_charge_retention", 100.0)
    rfc_fade = repeated_fc_result.metrics.get("stress_fade_rate", 0.0)
    rfc_r_growth = repeated_fc_result.metrics.get("resistance_growth_pct", 0.0)

    # Thermal stress metrics
    ts_fade = thermal_stress_result.metrics.get("stress_fade_rate", 0.0)
    ts_penalty = thermal_stress_result.metrics.get("stress_penalty_pct", 0.0)
    ts_retention = thermal_stress_result.metrics.get("capacity_retention", 100.0)

    # Cathode thermal stability metrics (2C/55C, 15 cycles)
    ct_retention = cathode_thermal_result.metrics.get("capacity_retention", 100.0)
    ct_fade = cathode_thermal_result.metrics.get("stress_fade_rate", 0.0)
    ct_penalty = cathode_thermal_result.metrics.get("stress_penalty_pct", 0.0)

    # Worst-case retention across all stress scenarios (including 3C stress + cathode thermal)
    standard_retention = aging_result.metrics.get("capacity_retention", 100.0)
    worst_stress_retention = min(
        standard_retention, fc_retention, ts_retention, rfc_retention, ct_retention,
    )

    return {
        "worst_case_capacity_delta": round(worst_delta, 4),
        "crate_sensitivity": round(crate_sensitivity, 4),
        "thermal_sensitivity": round(thermal_sensitivity, 4),
        "capacity_retention": standard_retention,
        "fade_rate": aging_result.metrics.get("fade_rate", 0.0),
        "fast_charge_fade_rate": round(fc_fade, 4),
        "fast_charge_penalty_pct": round(fc_penalty, 4),
        "repeated_fast_charge_retention": round(rfc_retention, 4),
        "repeated_fast_charge_fade_rate": round(rfc_fade, 4),
        "resistance_growth_pct": round(rfc_r_growth, 4),
        "thermal_stress_fade_rate": round(ts_fade, 4),
        "thermal_stress_penalty_pct": round(ts_penalty, 4),
        "cathode_thermal_retention": round(ct_retention, 4),
        "cathode_thermal_fade_rate": round(ct_fade, 4),
        "cathode_thermal_penalty_pct": round(ct_penalty, 4),
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
        # Base stress resilience: 100% → 1.0, 90% → 0.75, 70% → 0.25, 50% → 0.0
        stress_score = max(0.0, min(1.0, (wsr - 50.0) / 50.0))

        # Resistance growth penalty: penalize candidates whose impedance
        # grows significantly under fast-charge stress (>5% growth is a flag)
        r_growth = robustness_profile.get("resistance_growth_pct", 0)
        if r_growth > 5.0:
            r_growth_penalty = min(0.15, (r_growth - 5.0) / 50.0)
            stress_score = max(0.0, stress_score - r_growth_penalty)

        # Repeated fast-charge retention penalty: if 3C/30-cycle retention
        # is significantly worse than 2C/20-cycle, flag the degradation trend
        rfc_retention = robustness_profile.get("repeated_fast_charge_retention", 100)
        fc_retention_2c = robustness_profile.get("fast_charge_fade_rate", 0)
        if rfc_retention < 90.0:
            # Additional penalty for poor sustained fast-charge retention
            rfc_penalty = min(0.10, (90.0 - rfc_retention) / 100.0)
            stress_score = max(0.0, stress_score - rfc_penalty)

        components["stress_resilience"] = stress_score

        fc_fade = robustness_profile.get("fast_charge_fade_rate", 0)
        ts_fade = robustness_profile.get("thermal_stress_fade_rate", 0)
        fc_penalty = robustness_profile.get("fast_charge_penalty_pct", 0)
        ts_penalty = robustness_profile.get("thermal_stress_penalty_pct", 0)

        if fc_fade > 0.08:
            caveats.append(
                f"Fast-charge fragility: {fc_fade:.3f}%/cycle fade at 2C "
                f"(penalty {fc_penalty:.1f}% vs 1C baseline)"
            )
        rfc_fade = robustness_profile.get("repeated_fast_charge_fade_rate", 0)
        if rfc_fade > 0.06:
            caveats.append(
                f"Sustained fast-charge degradation: {rfc_fade:.3f}%/cycle at 3C "
                f"over 30 cycles (retention {rfc_retention:.1f}%)"
            )
        if r_growth > 5.0:
            caveats.append(
                f"Resistance growth under fast-charge: {r_growth:.1f}% increase "
                "after 3C stress cycling"
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
        # Resistance growth hard-fail: >20% impedance growth under
        # fast-charge stress indicates rapid electrode/SEI degradation
        if r_growth > 20.0:
            hard_fail = True
            hard_fail_reasons.append(
                f"Resistance growth {r_growth:.1f}% under fast-charge stress "
                "exceeds 20% limit — indicates accelerated impedance rise"
            )
    else:
        components["stress_resilience"] = 0.5

    # --- Rate-tradeoff collapse detection ---
    # If rate capability is poor AND resistance improvement is the main gain,
    # the candidate is not useful for fast-charge applications
    if (robustness_profile and "crate_sensitivity" in robustness_profile
            and robustness_profile["crate_sensitivity"] > 0.25):
        r_imp = components.get("resistance_improvement", 0)
        rate_cap = components.get("rate_capability", 0.5)
        if r_imp > 0.7 and rate_cap < 0.3:
            caveats.append(
                "Rate-tradeoff collapse: resistance improvement does not translate "
                f"to rate capability (C-rate sensitivity {robustness_profile['crate_sensitivity']:.1%})"
            )

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
        # Repeated fast-charge check: sustained degradation trend
        rfc_ret = robustness_profile.get("repeated_fast_charge_retention", 100)
        fc_ret_2c = 100.0 - robustness_profile.get("fast_charge_penalty_pct", 0) * 0.5
        if rfc_ret < 95.0 and rfc_ret < standard_ret - 2.0:
            caveats.append(
                f"Sustained fast-charge degradation: 3C retention ({rfc_ret:.1f}%) "
                f"below standard ({standard_ret:.1f}%) — fast-charge durability concern"
            )
        # Resistance growth warning
        r_growth = robustness_profile.get("resistance_growth_pct", 0)
        if r_growth > 3.0:
            caveats.append(
                f"Impedance growth: {r_growth:.1f}% resistance increase after "
                "fast-charge stress — may limit fast-charge cycle life"
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
    """Generate an explicit rejection reason for a near-miss or rejected candidate.

    Near-miss candidates (within ALTERNATE_MARGIN of threshold) get more detailed
    diagnostics explaining what would need to improve for promotion.
    """
    score = evaluation.final_score
    gap = promotion_threshold - score

    if evaluation.hard_fail:
        return f"Hard fail: {'; '.join(evaluation.hard_fail_reasons)}"

    components = evaluation.score_components or {}
    is_near_miss = gap < ALTERNATE_MARGIN

    parts = [f"Score {score:.4f} below threshold {promotion_threshold:.2f} (gap: {gap:.4f})"]

    if components:
        weakest = min(components, key=lambda k: components[k])
        strongest = max(components, key=lambda k: components[k])
        parts.append(f"weakest: {weakest} ({components[weakest]:.2f})")
        if is_near_miss:
            # Near-miss: explain what needs to improve
            parts.append(f"strongest: {strongest} ({components[strongest]:.2f})")
            below_half = [k for k, v in components.items() if v < 0.3]
            if below_half:
                parts.append(f"components below 0.3: {', '.join(below_half)}")

    if robustness_profile:
        wsr = robustness_profile.get("worst_stress_retention", 100)
        if wsr < 90:
            parts.append(f"stress-fragile (worst retention {wsr:.1f}%)")
        r_growth = robustness_profile.get("resistance_growth_pct", 0)
        if r_growth > 5.0:
            parts.append(f"resistance growth {r_growth:.1f}% under stress")
        rfc_ret = robustness_profile.get("repeated_fast_charge_retention", 100)
        if rfc_ret < 92:
            parts.append(f"poor fast-charge durability ({rfc_ret:.1f}% at 3C)")

    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Full battery optimization loop
# ---------------------------------------------------------------------------

ALTERNATE_MARGIN = 0.05

# ── Promotion selectivity (CC-BE-2470) ─────────────────────────────────────
# Evidence from battery_campaign_results.json (46 runs, 45 promoted):
#   Score floor ~0.72 (improved_efficiency), mean 0.826, max 0.861
#   100% promotion rate with threshold 0.55 — threshold far below score floor
#   Prior stress_resilience gate (0.40) never triggered (all candidates ~0.95)
#
# New defaults calibrated to reduce promotion rate to ~40-60%:
#   Baseline composite = 0.7195; prior scores: min 0.72, mean 0.826, max 0.861
#   At 0.84: ~50-60% promotion expected (validated by 30-seed sweep)
DEFAULT_PROMOTION_THRESHOLD = 0.84
STRESS_RESILIENCE_GATE = 0.60
REGIME_SPECIFICITY_MIN_FLOOR = 0.20  # was 0.15
# Baseline margin: candidate must beat baseline composite by this much
BASELINE_MARGIN = 0.08


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
        sidecar_result: Optional[PyBaMMSidecarResult] = None,
    ):
        self.candidate = candidate
        self.evaluation = evaluation
        self.decision = decision
        self.experiment_metrics = experiment_metrics
        self.robustness_profile = robustness_profile or {}
        self.promotion_caveats = promotion_caveats or []
        self.sidecar_result = sidecar_result


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
        promotion_threshold: float = DEFAULT_PROMOTION_THRESHOLD,
        base_params: Optional[dict] = None,
        seed: Optional[int] = None,
        sidecar=None,
    ):
        self.repo = repo
        self.n_candidates = n_candidates
        self.promotion_threshold = promotion_threshold
        self.base_params = base_params or dict(DEFAULT_CELL_PARAMS)
        self.seed = seed
        self.sidecar = sidecar  # Optional PyBaMMSidecar or MockPyBaMMSidecar

    def run(self, run_id: str = "") -> BatteryLoopResult:
        """Execute one full optimization loop iteration."""
        prior_lessons = self.repo.list_idea_memory("battery_ecm", limit=50)
        experiment_memories = self.repo.list_experiment_memory("battery_ecm", limit=50)

        # 1. Generate baseline
        logger.info("Running baseline battery experiment...")
        baseline_result = run_experiment("baseline_cycle", self.base_params)
        baseline_metrics = baseline_result.metrics

        # 1b. Pre-compute chemistry-specific baselines for cathode families
        # (CC-BE-2471: cathode candidates are scored against their own chemistry
        # baseline, not the generic NMC baseline, so resistance/capacity
        # improvements are measured relative to the chemistry's starting point)
        self._cathode_baselines: dict[str, dict] = {}
        for chem_key, profile in CATHODE_ECM_PROFILES.items():
            chem_baseline = run_experiment("baseline_cycle", profile["base_params"])
            self._cathode_baselines[chem_key] = chem_baseline.metrics

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

        # Collect candidates that pass all ECM gates (threshold + stress + regime)
        qualifying: list[BatteryCandidateResult] = []
        best = None
        alternate = None
        promoted_count = 0

        # Compute baseline composite score for margin comparison (CC-BE-2470)
        baseline_eval = score_battery_candidate(
            baseline_metrics, baseline_metrics,
            compute_robustness_profile(self.base_params, baseline_metrics),
        )
        baseline_score = baseline_eval.final_score

        for r in scorable:
            passes_threshold = r.evaluation.final_score >= self.promotion_threshold
            # Baseline margin gate (CC-BE-2470): candidate must beat baseline
            # composite score by BASELINE_MARGIN to demonstrate real improvement
            passes_margin = r.evaluation.final_score >= baseline_score + BASELINE_MARGIN
            # Stress gate: stress_resilience must meet STRESS_RESILIENCE_GATE
            stress_ok = r.evaluation.score_components.get("stress_resilience", 1.0) >= STRESS_RESILIENCE_GATE
            # Regime-specificity gate: if gains are concentrated in a single
            # component and the weakest component is below floor, the candidate
            # is regime-specific (only works in one operating condition)
            components = r.evaluation.score_components or {}
            regime_ok = True
            if components:
                comp_vals = [v for k, v in components.items() if k != "plausibility_penalty"]
                if comp_vals:
                    max_c = max(comp_vals)
                    min_c = min(comp_vals)
                    if max_c > 0.85 and min_c < REGIME_SPECIFICITY_MIN_FLOOR:
                        regime_ok = False

            if passes_threshold and passes_margin and stress_ok and regime_ok:
                qualifying.append(r)
            elif passes_threshold and not passes_margin:
                # Above threshold but too close to baseline — reject
                r.decision = PromotionDecision.REJECTED
                r.candidate.status = CandidateStatus.REJECTED
                r.candidate.rejection_reason = (
                    f"Score {r.evaluation.final_score:.4f} above threshold but "
                    f"only {r.evaluation.final_score - baseline_score:+.4f} vs baseline "
                    f"({baseline_score:.4f}) — below required margin of {BASELINE_MARGIN}"
                )
                self.repo.save_domain_candidate(r.candidate)
            elif passes_threshold and not stress_ok:
                # Above threshold but stress-fragile — reject with explicit reason
                r.decision = PromotionDecision.REJECTED
                r.candidate.status = CandidateStatus.REJECTED
                stress_score = r.evaluation.score_components.get("stress_resilience", 0)
                r.candidate.rejection_reason = (
                    f"Score {r.evaluation.final_score:.4f} above threshold but "
                    f"stress_resilience {stress_score:.2f} below {STRESS_RESILIENCE_GATE:.2f} minimum — "
                    "candidate is fragile under fast-charge or thermal stress"
                )
                self.repo.save_domain_candidate(r.candidate)
            elif passes_threshold and not regime_ok:
                # Above threshold but regime-specific — reject
                r.decision = PromotionDecision.REJECTED
                r.candidate.status = CandidateStatus.REJECTED
                weakest = min(components, key=lambda k: components[k]) if components else "unknown"
                strongest = max(components, key=lambda k: components[k]) if components else "unknown"
                r.candidate.rejection_reason = (
                    f"Score {r.evaluation.final_score:.4f} above threshold but "
                    f"regime-specific: {strongest} ({components.get(strongest, 0):.2f}) "
                    f"vs {weakest} ({components.get(weakest, 0):.2f}) — "
                    "gains disappear outside one operating regime"
                )
                self.repo.save_domain_candidate(r.candidate)

        # Sidecar-verified promotion: verify top-2 qualifying candidates,
        # promote first survivor
        best = self._finalize_promotion_with_sidecar(qualifying, baseline_metrics)
        if best is not None:
            promoted_count = 1
            # Select alternate from remaining qualifying candidates
            for r in qualifying:
                if r is best:
                    continue
                if (
                    alternate is None
                    and r.evaluation.final_score >= self.promotion_threshold - ALTERNATE_MARGIN
                    and r.candidate.family != best.candidate.family
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
                    break

        # Reject remaining qualifying candidates that were not promoted or alternated
        for r in qualifying:
            if r is best or r is alternate:
                continue
            r.decision = PromotionDecision.REJECTED
            r.candidate.status = CandidateStatus.REJECTED
            r.candidate.rejection_reason = generate_rejection_reason(
                r.candidate, r.evaluation, self.promotion_threshold,
                r.robustness_profile,
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

        # Resolve scoring baseline: cathode families use chemistry-specific
        # baselines (CC-BE-2471) so improvements are measured fairly
        scoring_baseline = baseline_metrics
        chem_key = _candidate_chemistry_key(candidate)
        if chem_key and hasattr(self, "_cathode_baselines") and chem_key in self._cathode_baselines:
            scoring_baseline = self._cathode_baselines[chem_key]

        # Run robustness profile (aging + C-rate + thermal)
        robustness = compute_robustness_profile(candidate.parameters, scoring_baseline)

        # Score
        eval_result = score_battery_candidate(
            cycle_result.metrics, scoring_baseline,
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

    # ── Sidecar verification hooks ──────────────────────────────────────

    def _verify_with_sidecar(
        self,
        candidate: CandidateSpec,
        ecm_metrics: dict,
        robustness_profile: Optional[dict] = None,
    ) -> PyBaMMSidecarResult:
        """Send candidate to sidecar for DFN verification.

        Enriches ecm_metrics with robustness data (high_rate_retention)
        for better concordance on rate-dependent behavior.

        Returns PyBaMMSidecarResult with status. If sidecar is None or
        unavailable, returns UNAVAILABLE status.
        """
        # Enrich ECM metrics with robustness data for concordance
        enriched_metrics = dict(ecm_metrics)
        if robustness_profile:
            rfc_ret = robustness_profile.get("repeated_fast_charge_retention")
            if rfc_ret is not None:
                enriched_metrics["high_rate_retention"] = rfc_ret

        if self.sidecar is None:
            return PyBaMMSidecarResult(
                candidate_id=candidate.id,
                status=SidecarStatus.UNAVAILABLE,
                ecm_metrics=enriched_metrics,
                error_message="No sidecar configured",
            )
        if not self.sidecar.is_available():
            return PyBaMMSidecarResult(
                candidate_id=candidate.id,
                status=SidecarStatus.UNAVAILABLE,
                ecm_metrics=enriched_metrics,
                error_message="Sidecar not available",
            )
        # Resolve chemistry and PyBaMM parameter set for cathode candidates
        chemistry = None
        pybamm_param_set = None
        family = candidate.family
        if family:
            family_def = next((f for f in CANDIDATE_FAMILIES if f["family"] == family), None)
            if family_def and "chemistry" in family_def:
                chem_key = family_def["chemistry"]
                chemistry = chem_key
                profile = CATHODE_ECM_PROFILES.get(chem_key, {})
                pybamm_param_set = profile.get("pybamm_parameter_set")

        return self.sidecar.verify_candidate(
            candidate_id=candidate.id,
            ecm_params=candidate.parameters,
            ecm_metrics=enriched_metrics,
            chemistry=chemistry,
            pybamm_parameter_set=pybamm_param_set,
        )

    def _apply_sidecar_verdict(
        self,
        result: BatteryCandidateResult,
        sidecar_result: PyBaMMSidecarResult,
    ) -> bool:
        """Apply concordance gate to a candidate.

        Returns True if candidate survives (should be promoted), False if vetoed.

        Decision logic by sidecar status:
        - SUCCESS + concordance >= 0.30 → survives (with caveat if < 0.60)
        - SUCCESS + concordance < 0.30  → vetoed
        - UNAVAILABLE                   → survives (ECM-only, no caveat)
        - ERROR                         → survives with caveat
        - INVALID                       → vetoed
        """
        result.sidecar_result = sidecar_result

        if sidecar_result.status == SidecarStatus.UNAVAILABLE:
            return True  # ECM-only path

        if sidecar_result.status == SidecarStatus.ERROR:
            result.promotion_caveats.append(
                f"Sidecar verification failed: {sidecar_result.error_message} "
                "— ECM-only promotion"
            )
            return True  # survives with caveat

        if sidecar_result.status == SidecarStatus.INVALID:
            return False  # vetoed

        # SUCCESS path — apply concordance gate
        conc = sidecar_result.concordance_score
        if conc < CONCORDANCE_VETO_THRESHOLD:
            return False  # vetoed
        if conc < CONCORDANCE_CONFIRM_THRESHOLD:
            result.promotion_caveats.append(
                f"Low PyBaMM concordance ({conc:.2f}) — "
                "ECM results may not hold under higher-fidelity modeling"
            )
        return True  # survives

    def _finalize_promotion_with_sidecar(
        self,
        qualifying: list[BatteryCandidateResult],
        baseline_metrics: dict,
    ) -> Optional[BatteryCandidateResult]:
        """Verify top-2 qualifying candidates through sidecar. Return first survivor.

        If sidecar is None or unavailable, falls through to current behavior
        (first qualifying candidate promoted).
        """
        # Take top 2 by ECM score
        top_n = qualifying[:2]

        for r in top_n:
            # Sidecar verification
            sidecar_result = self._verify_with_sidecar(
                r.candidate, r.experiment_metrics, r.robustness_profile,
            )
            survives = self._apply_sidecar_verdict(r, sidecar_result)

            if survives:
                r.decision = PromotionDecision.PROMOTED
                r.candidate.status = CandidateStatus.PROMOTED
                r.candidate.rejection_reason = ""
                self.repo.save_domain_candidate(r.candidate)
                r.promotion_caveats = (r.promotion_caveats or []) + generate_candidate_caveats(
                    r.candidate, r.evaluation, baseline_metrics,
                    r.experiment_metrics, r.robustness_profile,
                )
                return r
            else:
                # Vetoed by sidecar
                conc = sidecar_result.concordance_score
                r.decision = PromotionDecision.REJECTED
                r.candidate.status = CandidateStatus.REJECTED
                r.candidate.rejection_reason = (
                    f"Sidecar veto: PyBaMM concordance {conc:.2f} "
                    f"below {CONCORDANCE_VETO_THRESHOLD} threshold"
                    if sidecar_result.status == SidecarStatus.SUCCESS
                    else f"Sidecar veto ({sidecar_result.status.value}): {sidecar_result.error_message}"
                )
                self.repo.save_domain_candidate(r.candidate)

        return None  # No candidate survived

    # ── Memory persistence ───────────────────────────────────────────────

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

        # Battery-specific lesson extraction from robustness profile
        if robustness_profile:
            wsr = robustness_profile.get("worst_stress_retention", 100)
            fc_fade = robustness_profile.get("fast_charge_fade_rate", 0)
            ts_fade = robustness_profile.get("thermal_stress_fade_rate", 0)
            rfc_ret = robustness_profile.get("repeated_fast_charge_retention", 100)
            r_growth = robustness_profile.get("resistance_growth_pct", 0)
            standard_fade = robustness_profile.get("fade_rate", 0)

            if wsr < 90:
                lesson += f". Stress-fragile: worst retention {wsr:.1f}%"
            if fc_fade > 0.05:
                lesson += f". Fast-charge fade: {fc_fade:.3f}%/cycle"
            if rfc_ret < 95:
                lesson += f". Poor 3C durability: {rfc_ret:.1f}% retention"
            if r_growth > 5.0:
                lesson += f". Resistance growth: {r_growth:.1f}% under fast-charge"
            # Tradeoff lessons: improved in one dimension but degraded in another
            if standard_fade < 0.03 and fc_fade > 0.06:
                lesson += ". Tradeoff: good nominal fade but poor fast-charge durability"
            if components.get("resistance_improvement", 0) > 0.7 and components.get("rate_capability", 0.5) < 0.3:
                lesson += ". Tradeoff: low resistance but poor rate capability"

        family = candidate.family
        if not family:
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

        # Battery-specific weakness detection from robustness profile
        if robustness_profile and not weakness:
            wsr = robustness_profile.get("worst_stress_retention", 100)
            rfc_ret = robustness_profile.get("repeated_fast_charge_retention", 100)
            r_growth = robustness_profile.get("resistance_growth_pct", 0)

            if wsr < 85:
                weakness = f"Stress-fragile: worst retention {wsr:.1f}% under stress"
            elif rfc_ret < 92:
                weakness = f"Fast-charge weak: 3C retention {rfc_ret:.1f}%"
            elif r_growth > 8.0:
                weakness = f"Resistance growth: {r_growth:.1f}% impedance rise under fast-charge"

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

# Use shared benchmark report version from domain_models
from .domain_models import BENCHMARK_REPORT_VERSION


def run_battery_benchmark(
    repo: Repository,
    n_candidates: int = 6,
    seed: int = 42,
    promotion_threshold: float = DEFAULT_PROMOTION_THRESHOLD,
    sidecar=None,
) -> dict:
    """Run battery benchmark: full loop + held-out realism check + stress profile.

    The benchmark report is the primary regression-check artifact for the
    battery domain. It includes:
    - Baseline metrics
    - Best candidate with score, metrics, stress profile, and caveats
    - Reference comparison against held-out commercial cell parameters
    - Per-candidate breakdown for rejected/hard-fail analysis
    - Stability indicators for benchmark regression detection
    """
    loop = BatteryOptimizationLoop(
        repo, n_candidates=n_candidates,
        promotion_threshold=promotion_threshold, seed=seed,
        sidecar=sidecar,
    )
    result = loop.run(run_id=f"benchmark_{seed}")
    baseline = result.baseline_metrics

    # Held-out realism check against reference cell
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

    # Build stress profile summary for best candidate
    stress_profile: Optional[dict] = None
    if result.best_promoted and result.best_promoted.robustness_profile:
        rp = result.best_promoted.robustness_profile
        stress_profile = {
            "standard_retention": rp.get("capacity_retention", 0),
            "standard_fade_rate": rp.get("fade_rate", 0),
            "fast_charge_fade_rate": rp.get("fast_charge_fade_rate", 0),
            "fast_charge_penalty_pct": rp.get("fast_charge_penalty_pct", 0),
            "repeated_fast_charge_retention": rp.get("repeated_fast_charge_retention", 0),
            "repeated_fast_charge_fade_rate": rp.get("repeated_fast_charge_fade_rate", 0),
            "resistance_growth_pct": rp.get("resistance_growth_pct", 0),
            "thermal_stress_fade_rate": rp.get("thermal_stress_fade_rate", 0),
            "thermal_stress_penalty_pct": rp.get("thermal_stress_penalty_pct", 0),
            "worst_stress_retention": rp.get("worst_stress_retention", 0),
            "crate_sensitivity": rp.get("crate_sensitivity", 0),
            "thermal_sensitivity": rp.get("thermal_sensitivity", 0),
        }

    # Per-candidate breakdown
    candidate_breakdown = []
    for cr in result.candidates:
        entry: dict = {
            "title": cr.candidate.title,
            "score": cr.evaluation.final_score,
            "decision": cr.decision.value,
            "hard_fail": cr.evaluation.hard_fail,
        }
        if cr.evaluation.hard_fail:
            entry["hard_fail_reasons"] = cr.evaluation.hard_fail_reasons
        elif cr.decision.value == "rejected":
            entry["rejection_reason"] = cr.candidate.rejection_reason
        if cr.robustness_profile:
            entry["worst_stress_retention"] = cr.robustness_profile.get(
                "worst_stress_retention", None,
            )
        candidate_breakdown.append(entry)

    # Degradation profile: summarize degradation behavior across stress scenarios
    degradation_profile: Optional[dict] = None
    if result.best_promoted and result.best_promoted.robustness_profile:
        rp = result.best_promoted.robustness_profile
        degradation_profile = {
            "standard_fade_rate": rp.get("fade_rate", 0),
            "fast_charge_fade_rate_2c": rp.get("fast_charge_fade_rate", 0),
            "fast_charge_fade_rate_3c": rp.get("repeated_fast_charge_fade_rate", 0),
            "thermal_stress_fade_rate": rp.get("thermal_stress_fade_rate", 0),
            "resistance_growth_pct": rp.get("resistance_growth_pct", 0),
            "degradation_ratio_fc_vs_standard": (
                round(rp.get("fast_charge_fade_rate", 0) / rp["fade_rate"], 2)
                if rp.get("fade_rate", 0) > 0 else None
            ),
            "degradation_ratio_thermal_vs_standard": (
                round(rp.get("thermal_stress_fade_rate", 0) / rp["fade_rate"], 2)
                if rp.get("fade_rate", 0) > 0 else None
            ),
        }

    # Family/rationale summary across all candidates
    family_summary: dict[str, dict] = {}
    for cr in result.candidates:
        fam = cr.candidate.family or "unknown"
        if fam not in family_summary:
            family_summary[fam] = {"count": 0, "promoted": 0, "rejected": 0, "hard_fail": 0, "scores": []}
        family_summary[fam]["count"] += 1
        family_summary[fam]["scores"].append(cr.evaluation.final_score)
        if cr.decision == PromotionDecision.PROMOTED:
            family_summary[fam]["promoted"] += 1
        elif cr.evaluation.hard_fail:
            family_summary[fam]["hard_fail"] += 1
        else:
            family_summary[fam]["rejected"] += 1
    for fam_data in family_summary.values():
        scores = fam_data["scores"]
        fam_data["mean_score"] = round(sum(scores) / len(scores), 4) if scores else 0
        fam_data["max_score"] = round(max(scores), 4) if scores else 0
        del fam_data["scores"]

    report: dict = {
        "benchmark_version": BENCHMARK_REPORT_VERSION,
        "benchmark_domain": "battery_ecm",
        "seed": seed,
        "n_candidates": n_candidates,
        "promotion_threshold": promotion_threshold,
        "baseline_candidate": {
            "params": "DEFAULT_CELL_PARAMS",
            "baseline_metrics": baseline,
        },
        "best_candidate": None,
        "stress_profile": stress_profile,
        "degradation_profile": degradation_profile,
        "robustness_profile": None,
        "caveats": [],
        "promotion_decision": "none",
        "reference_comparison": reference_comparison,
        "candidate_breakdown": candidate_breakdown,
        "family_summary": family_summary,
        "summary": result.summary(),
    }

    if result.best_promoted:
        bp = result.best_promoted
        report["best_candidate"] = {
            "title": bp.candidate.title,
            "score": bp.evaluation.final_score,
            "metrics": bp.experiment_metrics,
            "family": bp.candidate.family or bp.candidate.title.split("variant")[0].replace("Battery ", "").strip(),
            "score_components": bp.evaluation.score_components,
            "rationale": bp.candidate.rationale,
        }
        report["robustness_profile"] = {
            k: v for k, v in bp.robustness_profile.items() if k != "sweep_data"
        }
        report["caveats"] = bp.promotion_caveats
        report["promotion_decision"] = "promoted"

        # Sidecar verification summary (additive, not in BENCHMARK_REPORT_REQUIRED_KEYS)
        if bp.sidecar_result is not None:
            report["sidecar_verification"] = {
                "status": bp.sidecar_result.status.value,
                "concordance_score": bp.sidecar_result.concordance_score,
                "pybamm_parameter_set": bp.sidecar_result.pybamm_parameter_set,
                "concordance_details": bp.sidecar_result.concordance_details,
                "duration_seconds": bp.sidecar_result.duration_seconds,
            }

    return report
