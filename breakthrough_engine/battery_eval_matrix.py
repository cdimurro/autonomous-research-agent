"""Battery V2 evaluation matrix — formal comparison of architecture modes.

Compares ECM-only, sidecar, cathode, and full Battery V2 configurations
across multiple seeds to measure whether added architecture improves
decision quality.

Modes:
    A. ecm_only          — baseline ECM loop, no sidecar, original 7 families
    B. ecm_mock_sidecar  — ECM + MockPyBaMMSidecar, original 7 families
    C. ecm_cathode       — ECM + all 11 families (incl. cathode), no sidecar
    D. full_v2_mock      — ECM + all 11 families + MockPyBaMMSidecar

Usage:
    from breakthrough_engine.battery_eval_matrix import run_eval_matrix
    results = run_eval_matrix(seeds=[42, 100, 200])
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .battery_loop import (
    CANDIDATE_FAMILIES,
    BatteryOptimizationLoop,
    run_battery_benchmark,
)
from .battery_sidecar import MockPyBaMMSidecar, SidecarStatus
from .db import Repository


# ---------------------------------------------------------------------------
# Mode definitions
# ---------------------------------------------------------------------------

EVAL_MODES = {
    "ecm_only": {
        "description": "Baseline ECM loop, no sidecar, original 7 families",
        "sidecar": None,
        "cathode_families": False,
    },
    "ecm_mock_sidecar": {
        "description": "ECM + mock sidecar verification, original 7 families",
        "sidecar": "mock",
        "cathode_families": False,
    },
    "ecm_cathode": {
        "description": "ECM + all 11 families (incl. cathode), no sidecar",
        "sidecar": None,
        "cathode_families": True,
    },
    "full_v2_mock": {
        "description": "Full Battery V2: ECM + all 11 families + mock sidecar",
        "sidecar": "mock",
        "cathode_families": True,
    },
}

# Indices of original 7 non-cathode families
_ORIGINAL_FAMILY_COUNT = 7


def _make_sidecar(mode_cfg: dict, seed: int):
    """Create sidecar instance for a mode."""
    if mode_cfg["sidecar"] == "mock":
        return MockPyBaMMSidecar(seed=seed)
    return None


def _filter_candidates_for_mode(mode_cfg: dict) -> int:
    """Return n_candidates appropriate for the mode.

    When cathode families are disabled, we use 6 candidates (from 7 families).
    When enabled, we use 8 candidates (from 11 families) to allow cathode
    families a fair chance of being sampled.
    """
    return 8 if mode_cfg["cathode_families"] else 6


# ---------------------------------------------------------------------------
# Single-mode run
# ---------------------------------------------------------------------------

def run_single_mode(
    repo: Repository,
    mode: str,
    seed: int,
    n_candidates: Optional[int] = None,
) -> dict:
    """Run a single evaluation mode at a single seed.

    Returns a structured result dict with metrics for comparison.
    """
    mode_cfg = EVAL_MODES[mode]
    sidecar = _make_sidecar(mode_cfg, seed)
    n = n_candidates or _filter_candidates_for_mode(mode_cfg)

    t0 = time.time()
    report = run_battery_benchmark(
        repo, n_candidates=n, seed=seed, sidecar=sidecar,
    )
    elapsed = time.time() - t0

    # Extract comparison metrics
    best = report.get("best_candidate")
    breakdown = report.get("candidate_breakdown", [])
    family_summary = report.get("family_summary", {})

    promoted_count = sum(1 for c in breakdown if c.get("decision") == "promoted")
    rejected_count = sum(1 for c in breakdown if c.get("decision") == "rejected")
    hard_fail_count = sum(1 for c in breakdown if c.get("hard_fail"))
    deferred_count = sum(1 for c in breakdown if c.get("decision") == "deferred")

    scores = [c.get("score", 0) for c in breakdown if not c.get("hard_fail")]

    # Sidecar-specific metrics
    sidecar_verification = report.get("sidecar_verification", {})
    sidecar_active = sidecar_verification.get("status") == "success"
    sidecar_concordance = sidecar_verification.get("concordance_score", 0)

    # Count sidecar vetoes/caveats from rejection reasons
    sidecar_veto_count = sum(
        1 for c in breakdown
        if "sidecar veto" in (c.get("rejection_reason") or "").lower()
    )
    sidecar_caveat_count = 0
    if report.get("caveats"):
        sidecar_caveat_count = sum(
            1 for cav in report["caveats"]
            if "concordance" in cav.lower() or "sidecar" in cav.lower()
        )

    # Chemistry family diversity
    cathode_families_present = [
        f for f in family_summary if f.startswith("cathode_")
    ]
    unique_families = list(family_summary.keys())

    # Reference envelope
    ref = report.get("reference_comparison", {})
    within_envelope = ref.get("within_reference_envelope", False)

    # Winner info
    winner_title = best["title"] if best else None
    winner_score = best["score"] if best else None
    winner_family = best.get("family") if best else None
    winner_is_cathode = (winner_family or "").startswith("cathode_")

    return {
        "mode": mode,
        "mode_description": mode_cfg["description"],
        "seed": seed,
        "n_candidates": n,
        "elapsed_seconds": round(elapsed, 2),
        # Promotion rates
        "promoted_count": promoted_count,
        "rejected_count": rejected_count,
        "hard_fail_count": hard_fail_count,
        "deferred_count": deferred_count,
        "promotion_rate": promoted_count / n if n > 0 else 0,
        # Score distribution
        "score_mean": round(sum(scores) / len(scores), 4) if scores else 0,
        "score_max": round(max(scores), 4) if scores else 0,
        "score_min": round(min(scores), 4) if scores else 0,
        # Family diversity
        "unique_families": unique_families,
        "unique_family_count": len(unique_families),
        "cathode_families_present": cathode_families_present,
        "cathode_family_count": len(cathode_families_present),
        # Sidecar
        "sidecar_active": sidecar_active,
        "sidecar_concordance": sidecar_concordance,
        "sidecar_veto_count": sidecar_veto_count,
        "sidecar_caveat_count": sidecar_caveat_count,
        # Reference envelope
        "within_reference_envelope": within_envelope,
        # Winner
        "winner_title": winner_title,
        "winner_score": winner_score,
        "winner_family": winner_family,
        "winner_is_cathode": winner_is_cathode,
        # Full report (for deeper inspection)
        "full_report": report,
    }


# ---------------------------------------------------------------------------
# Matrix runner
# ---------------------------------------------------------------------------

def run_eval_matrix(
    seeds: Optional[list[int]] = None,
    modes: Optional[list[str]] = None,
    n_candidates: Optional[int] = None,
) -> dict:
    """Run the full evaluation matrix across modes and seeds.

    Each (mode, seed) combination gets its own fresh Repository to ensure
    no memory bleed between runs.

    Returns structured comparison artifact.
    """
    from .db import init_db

    seeds = seeds or [42, 100, 200]
    modes = modes or list(EVAL_MODES.keys())

    results: list[dict] = []
    t0 = time.time()

    for mode in modes:
        for seed in seeds:
            db = init_db(in_memory=True)
            repo = Repository(db)
            result = run_single_mode(repo, mode, seed, n_candidates)
            # Strip full_report for the summary (too large for matrix view)
            result_summary = {k: v for k, v in result.items() if k != "full_report"}
            results.append(result_summary)

    total_elapsed = time.time() - t0

    # Compute cross-mode comparisons
    comparison = _compute_comparison(results, modes, seeds)

    return {
        "eval_matrix_version": 1,
        "modes": modes,
        "seeds": seeds,
        "total_runs": len(results),
        "total_elapsed_seconds": round(total_elapsed, 2),
        "results": results,
        "comparison": comparison,
    }


def _compute_comparison(
    results: list[dict],
    modes: list[str],
    seeds: list[int],
) -> dict:
    """Compute cross-mode summary statistics."""
    mode_stats: dict[str, dict] = {}

    for mode in modes:
        mode_results = [r for r in results if r["mode"] == mode]
        if not mode_results:
            continue

        scores = [r["score_max"] for r in mode_results]
        promo_rates = [r["promotion_rate"] for r in mode_results]
        winners = [r["winner_family"] for r in mode_results if r["winner_family"]]
        cathode_wins = sum(1 for r in mode_results if r["winner_is_cathode"])
        sidecar_vetoes = sum(r["sidecar_veto_count"] for r in mode_results)
        sidecar_caveats = sum(r["sidecar_caveat_count"] for r in mode_results)
        envelope_passes = sum(1 for r in mode_results if r["within_reference_envelope"])
        elapsed = [r["elapsed_seconds"] for r in mode_results]

        mode_stats[mode] = {
            "n_runs": len(mode_results),
            "mean_best_score": round(sum(scores) / len(scores), 4),
            "mean_promotion_rate": round(sum(promo_rates) / len(promo_rates), 4),
            "unique_winners": list(set(winners)),
            "cathode_win_count": cathode_wins,
            "total_sidecar_vetoes": sidecar_vetoes,
            "total_sidecar_caveats": sidecar_caveats,
            "envelope_pass_rate": round(envelope_passes / len(mode_results), 4),
            "mean_elapsed_seconds": round(sum(elapsed) / len(elapsed), 2),
        }

    # Cross-mode winner change detection
    winner_changes = []
    for seed in seeds:
        seed_results = {r["mode"]: r for r in results if r["seed"] == seed}
        ecm_winner = seed_results.get("ecm_only", {}).get("winner_family")
        for mode in modes:
            if mode == "ecm_only":
                continue
            mode_winner = seed_results.get(mode, {}).get("winner_family")
            if mode_winner != ecm_winner:
                winner_changes.append({
                    "seed": seed,
                    "mode": mode,
                    "ecm_winner": ecm_winner,
                    "mode_winner": mode_winner,
                })

    return {
        "mode_stats": mode_stats,
        "winner_changes": winner_changes,
        "sidecar_changed_winner": len([
            w for w in winner_changes if "sidecar" in w["mode"]
        ]) > 0,
        "cathode_changed_winner": len([
            w for w in winner_changes if "cathode" in w["mode"]
        ]) > 0,
    }


def save_eval_matrix_artifact(
    matrix: dict,
    output_dir: Optional[str] = None,
) -> str:
    """Save evaluation matrix artifact to disk."""
    out = Path(output_dir or "runtime/battery_eval")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "battery_eval_matrix.json"
    with open(path, "w") as f:
        json.dump(matrix, f, indent=2, default=str)
    return str(path)
