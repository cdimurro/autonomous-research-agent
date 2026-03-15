"""Battery architecture value report — decision-grade technical validation.

Takes evaluation matrix output and produces a structured report answering:
- Does the sidecar improve selection quality?
- Do cathode-focused families improve search quality?
- When does the sidecar veto or caveat matter?
- How much complexity was added vs value gained?
- How does full Battery V2 compare against ECM-only?

This is an internal evaluation brief for architecture decisions, not marketing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def generate_value_report(matrix: dict) -> dict:
    """Generate a decision-grade architecture value report from eval matrix.

    Args:
        matrix: Output from run_eval_matrix()

    Returns:
        Structured value report dict.
    """
    comparison = matrix.get("comparison", {})
    mode_stats = comparison.get("mode_stats", {})
    winner_changes = comparison.get("winner_changes", [])
    results = matrix.get("results", [])

    ecm = mode_stats.get("ecm_only", {})
    sidecar = mode_stats.get("ecm_mock_sidecar", {})
    cathode = mode_stats.get("ecm_cathode", {})
    full = mode_stats.get("full_v2_mock", {})

    # Section 1: Score comparison
    score_comparison = {}
    for mode_name, stats in mode_stats.items():
        score_comparison[mode_name] = {
            "mean_best_score": stats.get("mean_best_score", 0),
            "mean_promotion_rate": stats.get("mean_promotion_rate", 0),
            "envelope_pass_rate": stats.get("envelope_pass_rate", 0),
        }

    # Section 2: Sidecar impact
    sidecar_impact = {
        "sidecar_changed_winner": comparison.get("sidecar_changed_winner", False),
        "total_vetoes": sidecar.get("total_sidecar_vetoes", 0) + full.get("total_sidecar_vetoes", 0),
        "total_caveats": sidecar.get("total_sidecar_caveats", 0) + full.get("total_sidecar_caveats", 0),
        "score_delta_vs_ecm": round(
            sidecar.get("mean_best_score", 0) - ecm.get("mean_best_score", 0), 4
        ) if ecm and sidecar else None,
        "assessment": _assess_sidecar(ecm, sidecar, full, winner_changes),
    }

    # Section 3: Cathode family impact
    cathode_impact = {
        "cathode_changed_winner": comparison.get("cathode_changed_winner", False),
        "cathode_wins_ecm_cathode": cathode.get("cathode_win_count", 0),
        "cathode_wins_full_v2": full.get("cathode_win_count", 0),
        "unique_winners_ecm_only": ecm.get("unique_winners", []),
        "unique_winners_with_cathode": cathode.get("unique_winners", []),
        "score_delta_vs_ecm": round(
            cathode.get("mean_best_score", 0) - ecm.get("mean_best_score", 0), 4
        ) if ecm and cathode else None,
        "assessment": _assess_cathode(ecm, cathode, full, winner_changes),
    }

    # Section 4: Full V2 vs ECM-only
    full_vs_ecm = {
        "ecm_mean_score": ecm.get("mean_best_score", 0),
        "full_v2_mean_score": full.get("mean_best_score", 0),
        "score_delta": round(
            full.get("mean_best_score", 0) - ecm.get("mean_best_score", 0), 4
        ) if ecm and full else None,
        "ecm_promotion_rate": ecm.get("mean_promotion_rate", 0),
        "full_v2_promotion_rate": full.get("mean_promotion_rate", 0),
        "assessment": _assess_full_v2(ecm, full),
    }

    # Section 5: Runtime tradeoffs
    runtime_tradeoffs = {}
    for mode_name, stats in mode_stats.items():
        runtime_tradeoffs[mode_name] = {
            "mean_elapsed_seconds": stats.get("mean_elapsed_seconds", 0),
        }

    # Section 6: Winner change detail
    winner_change_detail = winner_changes

    # Section 7: Recommendation
    recommendation = _generate_recommendation(
        ecm, sidecar, cathode, full, winner_changes,
    )

    return {
        "report_type": "battery_architecture_value_report",
        "report_version": 1,
        "modes_compared": list(mode_stats.keys()),
        "seeds_used": matrix.get("seeds", []),
        "total_runs": matrix.get("total_runs", 0),
        "sections": {
            "score_comparison": score_comparison,
            "sidecar_impact": sidecar_impact,
            "cathode_family_impact": cathode_impact,
            "full_v2_vs_ecm": full_vs_ecm,
            "runtime_tradeoffs": runtime_tradeoffs,
            "winner_changes": winner_change_detail,
        },
        "recommendation": recommendation,
    }


def _assess_sidecar(ecm: dict, sidecar: dict, full: dict, changes: list) -> str:
    if not ecm or not sidecar:
        return "Insufficient data to assess sidecar impact."
    vetoes = sidecar.get("total_sidecar_vetoes", 0) + full.get("total_sidecar_vetoes", 0)
    score_delta = sidecar.get("mean_best_score", 0) - ecm.get("mean_best_score", 0)
    sidecar_changes = [c for c in changes if "sidecar" in c["mode"]]
    if vetoes > 0 and len(sidecar_changes) > 0:
        return (
            f"Sidecar vetoed {vetoes} candidate(s) and changed the winner in "
            f"{len(sidecar_changes)} seed(s). Score delta: {score_delta:+.4f}. "
            "The sidecar is actively filtering candidates."
        )
    if vetoes > 0:
        return (
            f"Sidecar vetoed {vetoes} candidate(s) but did not change the winner. "
            f"Score delta: {score_delta:+.4f}. "
            "Sidecar provides a safety gate without disrupting promotion."
        )
    return (
        f"Sidecar did not veto any candidates. Score delta: {score_delta:+.4f}. "
        "ECM and sidecar agree on candidate quality."
    )


def _assess_cathode(ecm: dict, cathode: dict, full: dict, changes: list) -> str:
    if not ecm or not cathode:
        return "Insufficient data to assess cathode impact."
    cathode_wins = cathode.get("cathode_win_count", 0) + full.get("cathode_win_count", 0)
    cathode_changes = [c for c in changes if "cathode" in c["mode"]]
    score_delta = cathode.get("mean_best_score", 0) - ecm.get("mean_best_score", 0)
    if cathode_wins > 0:
        return (
            f"Cathode families won {cathode_wins} run(s). "
            f"Score delta vs ECM-only: {score_delta:+.4f}. "
            "Chemistry-anchored generation produces competitive candidates."
        )
    return (
        f"No cathode family won any run. Score delta: {score_delta:+.4f}. "
        "Original ECM-perturbation families remain dominant at current parameter ranges."
    )


def _assess_full_v2(ecm: dict, full: dict) -> str:
    if not ecm or not full:
        return "Insufficient data."
    delta = full.get("mean_best_score", 0) - ecm.get("mean_best_score", 0)
    if delta > 0.02:
        return f"Full V2 improves mean best score by {delta:+.4f} over ECM-only. Material improvement."
    elif delta > 0:
        return f"Full V2 shows marginal improvement ({delta:+.4f}). Architecture adds value but modestly."
    else:
        return f"Full V2 does not outperform ECM-only ({delta:+.4f}). Review configuration."


def _generate_recommendation(
    ecm: dict, sidecar: dict, cathode: dict, full: dict, changes: list,
) -> str:
    parts = []
    if full and ecm:
        delta = full.get("mean_best_score", 0) - ecm.get("mean_best_score", 0)
        if delta > 0:
            parts.append(
                f"Full Battery V2 path (sidecar + cathode) shows {delta:+.4f} "
                "score improvement over ECM-only baseline."
            )
        else:
            parts.append(
                "Full Battery V2 path does not yet show clear score improvement. "
                "Consider tuning concordance thresholds or cathode profiles."
            )
    vetoes = (
        sidecar.get("total_sidecar_vetoes", 0) + full.get("total_sidecar_vetoes", 0)
    ) if sidecar and full else 0
    if vetoes > 0:
        parts.append(f"Sidecar produced {vetoes} veto(es), providing active quality filtering.")
    else:
        parts.append("Sidecar did not veto any candidates — ECM screening is already conservative.")

    cathode_wins = (
        cathode.get("cathode_win_count", 0) + full.get("cathode_win_count", 0)
    ) if cathode and full else 0
    if cathode_wins > 0:
        parts.append(f"Cathode families won {cathode_wins} run(s), expanding the search space productively.")
    else:
        parts.append("Cathode families did not win any runs. Profiles may need tuning.")

    return " ".join(parts)


def save_value_report(report: dict, output_dir: Optional[str] = None) -> str:
    """Save value report artifact to disk."""
    out = Path(output_dir or "runtime/battery_eval")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "battery_value_report.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    return str(path)
