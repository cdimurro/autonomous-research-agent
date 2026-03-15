"""Battery Decision Brief — first human-facing product artifact.

Translates promoted battery results into a structured artifact that a
founder, researcher, engineer, or investor can understand quickly.

Machine-readable fields alongside human-readable summaries.
Can later be rendered in a UI.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .domain_models import new_id


class BatteryDecisionBrief(BaseModel):
    """Structured decision brief for a promoted battery candidate."""

    # Identity
    id: str = Field(default_factory=new_id)
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    # Headline
    title: str
    headline: str  # one-sentence summary

    # Candidate summary
    candidate_id: str = ""
    candidate_family: str = ""
    chemistry: Optional[str] = None
    profile_confidence: Optional[str] = None  # literature-backed / heuristic

    # What changed
    key_changes: list[str] = Field(default_factory=list)

    # Why promising
    why_promising: str = ""

    # Score
    final_score: float = 0.0
    score_components: dict = Field(default_factory=dict)
    score_summary: str = ""

    # Fast-charge behavior
    fast_charge_summary: str = ""
    fast_charge_retention: Optional[float] = None
    resistance_growth_pct: Optional[float] = None

    # Degradation / stress
    degradation_summary: str = ""
    worst_stress_retention: Optional[float] = None
    cathode_thermal_retention: Optional[float] = None

    # Sidecar verification (v2: includes concordance interpretation)
    sidecar_status: str = "not_verified"  # success / unavailable / error / invalid / not_verified
    sidecar_concordance: Optional[float] = None
    sidecar_gate_decision: str = ""  # confirmed / caveat / veto / not_verified
    sidecar_summary: str = ""
    sidecar_what_it_means: str = ""  # human-readable interpretation
    sidecar_concordance_details: dict = Field(default_factory=dict)  # per-metric breakdown

    # Caveats
    caveats: list[str] = Field(default_factory=list)

    # Why it beat alternatives
    vs_alternatives: str = ""

    # Recommended next action
    recommended_action: str = ""

    # Confidence tier
    confidence_tier: str = "standard"  # standard / high / low / unverified

    # Review state (for workflow integration)
    review_state: str = "awaiting_review"

    # Machine-readable reference data
    benchmark_seed: Optional[int] = None
    run_id: str = ""
    parameters: dict = Field(default_factory=dict)
    baseline_metrics: dict = Field(default_factory=dict)
    candidate_metrics: dict = Field(default_factory=dict)


def generate_decision_brief(report: dict) -> Optional[BatteryDecisionBrief]:
    """Generate a Battery Decision Brief from a benchmark report.

    Args:
        report: Output from run_battery_benchmark()

    Returns:
        BatteryDecisionBrief if a candidate was promoted, None otherwise.
    """
    best = report.get("best_candidate")
    if not best:
        return None

    family = best.get("family", "")
    score = best.get("score", 0)
    components = best.get("score_components", {})
    metrics = best.get("metrics", {})
    rationale = best.get("rationale", "")
    baseline = report.get("baseline_candidate", {}).get("baseline_metrics", {})
    stress = report.get("stress_profile") or {}
    degradation = report.get("degradation_profile") or {}
    robustness = report.get("robustness_profile") or {}
    sidecar_v = report.get("sidecar_verification") or {}
    caveats = report.get("caveats", [])
    breakdown = report.get("candidate_breakdown", [])
    ref = report.get("reference_comparison", {})

    # Chemistry detection
    chemistry = None
    profile_confidence = None
    if family.startswith("cathode_"):
        chemistry = _family_to_chemistry(family)
        if "heuristic" in rationale:
            profile_confidence = "heuristic"
        elif "literature-backed" in rationale:
            profile_confidence = "literature-backed"

    # Key changes
    key_changes = _compute_key_changes(metrics, baseline)

    # Headline
    headline = _generate_headline(family, score, chemistry, metrics, baseline)

    # Why promising
    why = _generate_why_promising(components, metrics, baseline, stress)

    # Score summary
    score_summary = _generate_score_summary(score, components)

    # Fast-charge summary
    fc_ret = stress.get("repeated_fast_charge_retention")
    r_growth = stress.get("resistance_growth_pct")
    fc_summary = _generate_fast_charge_summary(fc_ret, r_growth, stress)

    # Degradation summary
    worst_ret = stress.get("worst_stress_retention")
    ct_ret = robustness.get("cathode_thermal_retention")
    deg_summary = _generate_degradation_summary(degradation, worst_ret, ct_ret)

    # Sidecar (v2: enhanced with concordance interpretation)
    sc_status = sidecar_v.get("status", "not_verified")
    sc_conc = sidecar_v.get("concordance_score")
    sc_details = sidecar_v.get("concordance_details", {})
    sc_summary = _generate_sidecar_summary(sc_status, sc_conc)
    sc_gate = _compute_gate_decision(sc_status, sc_conc)
    sc_meaning = _generate_sidecar_meaning(sc_status, sc_conc, sc_details)

    # Vs alternatives
    vs_alt = _generate_vs_alternatives(best, breakdown)

    # Confidence tier
    confidence = _compute_confidence_tier(score, sc_status, sc_conc, profile_confidence)

    # Recommended action
    action = _generate_recommended_action(confidence, sc_status, caveats)

    # Title
    title = f"Battery Decision Brief: {best.get('title', family)}"

    return BatteryDecisionBrief(
        title=title,
        headline=headline,
        candidate_id=best.get("title", ""),
        candidate_family=family,
        chemistry=chemistry,
        profile_confidence=profile_confidence,
        key_changes=key_changes,
        why_promising=why,
        final_score=score,
        score_components=components,
        score_summary=score_summary,
        fast_charge_summary=fc_summary,
        fast_charge_retention=fc_ret,
        resistance_growth_pct=r_growth,
        degradation_summary=deg_summary,
        worst_stress_retention=worst_ret,
        cathode_thermal_retention=ct_ret,
        sidecar_status=sc_status,
        sidecar_concordance=sc_conc,
        sidecar_gate_decision=sc_gate,
        sidecar_summary=sc_summary,
        sidecar_what_it_means=sc_meaning,
        sidecar_concordance_details=sc_details,
        caveats=caveats,
        vs_alternatives=vs_alt,
        recommended_action=action,
        confidence_tier=confidence,
        benchmark_seed=report.get("seed"),
        run_id=report.get("summary", {}).get("run_id", ""),
        parameters=best.get("metrics", {}),
        baseline_metrics=baseline,
        candidate_metrics=metrics,
    )


# ---------------------------------------------------------------------------
# Generators for human-readable sections
# ---------------------------------------------------------------------------

def _family_to_chemistry(family: str) -> Optional[str]:
    mapping = {
        "cathode_high_ni": "NMC-811",
        "cathode_lfp": "LFP",
        "cathode_lmfp": "LMFP",
        "cathode_nmc532": "NMC-532",
    }
    return mapping.get(family)


def _compute_key_changes(metrics: dict, baseline: dict) -> list[str]:
    changes = []
    for key, label in [
        ("discharge_capacity", "Capacity"),
        ("internal_resistance", "Resistance"),
        ("coulombic_efficiency", "Coulombic efficiency"),
    ]:
        cand = metrics.get(key)
        base = baseline.get(key)
        if cand is not None and base is not None and base != 0:
            delta_pct = (cand - base) / abs(base) * 100
            direction = "improved" if (
                (delta_pct > 0 and key != "internal_resistance") or
                (delta_pct < 0 and key == "internal_resistance")
            ) else "degraded"
            changes.append(f"{label}: {delta_pct:+.1f}% ({direction})")
    return changes


def _generate_headline(
    family: str, score: float, chemistry: Optional[str],
    metrics: dict, baseline: dict,
) -> str:
    cap = metrics.get("discharge_capacity", 0)
    base_cap = baseline.get("discharge_capacity", 0)
    cap_delta = ((cap - base_cap) / base_cap * 100) if base_cap > 0 else 0

    chem_label = f" ({chemistry})" if chemistry else ""
    return (
        f"{family}{chem_label} candidate scored {score:.3f} with "
        f"{cap_delta:+.1f}% capacity change vs baseline."
    )


def _generate_why_promising(
    components: dict, metrics: dict, baseline: dict, stress: dict,
) -> str:
    strengths = sorted(components.items(), key=lambda x: x[1], reverse=True)[:3]
    parts = []
    for comp, val in strengths:
        if val > 0.5:
            parts.append(f"{comp} ({val:.2f})")
    if not parts:
        return "No standout strengths identified."
    return f"Strongest scoring components: {', '.join(parts)}."


def _generate_score_summary(score: float, components: dict) -> str:
    if score >= 0.7:
        tier = "Strong"
    elif score >= 0.55:
        tier = "Above threshold"
    else:
        tier = "Below threshold"
    n_above_half = sum(1 for v in components.values() if v > 0.5)
    return f"{tier} ({score:.3f}). {n_above_half}/{len(components)} components above 0.5."


def _generate_fast_charge_summary(
    fc_ret: Optional[float], r_growth: Optional[float], stress: dict,
) -> str:
    parts = []
    if fc_ret is not None:
        if fc_ret >= 95:
            parts.append(f"Excellent 3C retention ({fc_ret:.1f}%)")
        elif fc_ret >= 90:
            parts.append(f"Good 3C retention ({fc_ret:.1f}%)")
        else:
            parts.append(f"Weak 3C retention ({fc_ret:.1f}%)")
    if r_growth is not None:
        if r_growth <= 5:
            parts.append(f"low impedance growth ({r_growth:.1f}%)")
        elif r_growth <= 15:
            parts.append(f"moderate impedance growth ({r_growth:.1f}%)")
        else:
            parts.append(f"high impedance growth ({r_growth:.1f}%)")
    return "; ".join(parts) if parts else "Fast-charge data not available."


def _generate_degradation_summary(
    degradation: dict, worst_ret: Optional[float], ct_ret: Optional[float],
) -> str:
    parts = []
    if worst_ret is not None:
        parts.append(f"Worst-case stress retention: {worst_ret:.1f}%")
    if ct_ret is not None:
        parts.append(f"Cathode thermal retention (2C/55C): {ct_ret:.1f}%")
    std_fade = degradation.get("standard_fade_rate")
    if std_fade is not None:
        parts.append(f"Standard fade: {std_fade:.3f}%/cycle")
    return ". ".join(parts) if parts else "Degradation data not available."


def _generate_sidecar_summary(status: str, concordance: Optional[float]) -> str:
    if status == "not_verified":
        return "Not verified by PyBaMM sidecar (ECM-only)."
    if status == "success" and concordance is not None:
        if concordance >= 0.60:
            return f"Confirmed by PyBaMM DFN (concordance: {concordance:.2f})."
        elif concordance >= 0.30:
            return f"Passed with caveat (concordance: {concordance:.2f}). ECM results may not fully hold."
        else:
            return f"Vetoed by PyBaMM (concordance: {concordance:.2f}). Should not have been promoted."
    if status == "unavailable":
        return "PyBaMM sidecar unavailable. ECM-only evaluation."
    if status == "error":
        return "PyBaMM sidecar encountered an error. Treat as ECM-only."
    return f"Sidecar status: {status}."


def _generate_vs_alternatives(best: dict, breakdown: list) -> str:
    others = [c for c in breakdown if c.get("title") != best.get("title")]
    if not others:
        return "No alternatives to compare."
    n_rejected = sum(1 for c in others if c.get("decision") == "rejected")
    n_hard_fail = sum(1 for c in others if c.get("hard_fail"))
    runner_up = max(
        (c for c in others if not c.get("hard_fail")),
        key=lambda c: c.get("score", 0),
        default=None,
    )
    parts = [f"Beat {n_rejected} rejected and {n_hard_fail} hard-fail candidates."]
    if runner_up:
        gap = best.get("score", 0) - runner_up.get("score", 0)
        parts.append(
            f"Runner-up: {runner_up.get('title', '?')} "
            f"(score {runner_up.get('score', 0):.3f}, gap {gap:+.3f})."
        )
    return " ".join(parts)


def _compute_confidence_tier(
    score: float, sc_status: str, sc_conc: Optional[float],
    profile_confidence: Optional[str],
) -> str:
    if sc_status == "success" and sc_conc is not None and sc_conc >= 0.60 and score >= 0.65:
        return "high"
    if sc_status == "not_verified" or sc_status == "unavailable":
        if score >= 0.65:
            return "standard"
        return "low"
    if profile_confidence == "heuristic":
        return "low"
    if score >= 0.55:
        return "standard"
    return "low"


def _compute_gate_decision(status: str, concordance: Optional[float]) -> str:
    if status == "not_verified" or status == "unavailable":
        return "not_verified"
    if status == "error":
        return "not_verified"
    if status == "invalid":
        return "veto"
    if status == "success" and concordance is not None:
        if concordance >= 0.60:
            return "confirmed"
        elif concordance >= 0.30:
            return "caveat"
        else:
            return "veto"
    return "not_verified"


def _generate_sidecar_meaning(
    status: str, concordance: Optional[float], details: dict,
) -> str:
    if status == "not_verified" or status == "unavailable":
        return (
            "This candidate was evaluated by the ECM model only. "
            "Running PyBaMM sidecar verification would increase confidence."
        )
    if status == "error":
        return (
            "The PyBaMM sidecar encountered an error during verification. "
            "The candidate's ECM results are still valid but unverified by a richer model."
        )
    if status == "invalid":
        return (
            "The PyBaMM sidecar rejected this candidate's parameters as physically invalid. "
            "The ECM results may not reflect real cell behavior."
        )
    if status != "success" or concordance is None:
        return "Sidecar status unclear."

    # Success path — interpret concordance
    parts = []
    if concordance >= 0.60:
        parts.append(
            f"The PyBaMM DFN model confirms this candidate (concordance: {concordance:.2f}). "
            "ECM and DFN agree on key battery metrics."
        )
    elif concordance >= 0.30:
        parts.append(
            f"The PyBaMM DFN model partially agrees with the ECM (concordance: {concordance:.2f}). "
            "Some metrics diverge — review the per-metric breakdown."
        )
    else:
        parts.append(
            f"The PyBaMM DFN model strongly disagrees with the ECM (concordance: {concordance:.2f}). "
            "This candidate's predicted performance may not hold under higher-fidelity modeling."
        )

    # Add per-metric insight if available
    if details:
        high_agreement = []
        low_agreement = []
        for metric, info in details.items():
            agreement = info.get("agreement")
            if agreement is None:
                continue
            if agreement >= 0.8:
                high_agreement.append(metric)
            elif agreement < 0.5:
                low_agreement.append(metric)
        if high_agreement:
            parts.append(f"Strong agreement on: {', '.join(high_agreement)}.")
        if low_agreement:
            parts.append(f"Weak agreement on: {', '.join(low_agreement)}.")

    return " ".join(parts)


def _generate_recommended_action(
    confidence: str, sc_status: str, caveats: list[str],
) -> str:
    if confidence == "high":
        return "Candidate is ready for deeper experimental validation or engineering review."
    if confidence == "standard":
        if sc_status in ("not_verified", "unavailable"):
            return "Run PyBaMM sidecar verification to increase confidence before promotion."
        return "Review caveats. Consider targeted stress testing before advancing."
    return "Low confidence. Investigate caveats and consider re-running with different parameters."


def save_decision_brief(
    brief: BatteryDecisionBrief,
    output_dir: Optional[str] = None,
) -> str:
    """Save decision brief artifact to disk."""
    out = Path(output_dir or "runtime/battery_briefs")
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"brief_{brief.id}.json"
    with open(path, "w") as f:
        json.dump(brief.model_dump(), f, indent=2, default=str)
    return str(path)
