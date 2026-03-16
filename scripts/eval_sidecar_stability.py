#!/usr/bin/env python3
"""PyBaMM sidecar stability checkpoint.

Runs the live sidecar against a set of representative candidates
across multiple chemistries/families to assess stability.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/eval_sidecar_stability.py
"""

import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from breakthrough_engine.battery_sidecar import (
    PyBaMMSidecar,
    CONCORDANCE_VETO_THRESHOLD,
    CONCORDANCE_CONFIRM_THRESHOLD,
)
from breakthrough_engine.battery_loop import (
    generate_battery_candidates,
    DEFAULT_CELL_PARAMS,
)
from breakthrough_engine.battery_domain import run_experiment
from breakthrough_engine.db import Repository, init_db

import random


# Test matrix: varied seeds and candidate counts to get diverse candidates
TEST_CONFIGS = [
    {"seed": 500, "n": 6},
    {"seed": 501, "n": 6},
    {"seed": 502, "n": 6},
    {"seed": 503, "n": 8},  # More candidates = more cathode exposure
    {"seed": 504, "n": 8},
    {"seed": 505, "n": 8},
]


def run_sidecar_stability():
    sidecar = PyBaMMSidecar()

    # Health check first
    health = sidecar.check_health()
    print(f"Sidecar health: {json.dumps(health, default=str)}")
    if not health.get("available"):
        print("SIDECAR NOT AVAILABLE — aborting")
        return

    db = init_db()
    repo = Repository(db)

    results = []
    errors = []

    # Generate a diverse set of candidates
    all_candidates = []  # list of (CandidateSpec, seed)
    for cfg in TEST_CONFIGS:
        candidates = generate_battery_candidates(
            n_candidates=cfg["n"],
            seed=cfg["seed"],
        )
        for c in candidates:
            all_candidates.append((c, cfg["seed"]))

    print(f"\nTotal candidates to verify: {len(all_candidates)}")
    family_counts = Counter(c.family for c, _ in all_candidates)
    print(f"Family distribution: {dict(family_counts)}")

    # Run sidecar verification for each candidate
    print("\nRunning live sidecar verification...")
    for i, (cand, test_seed) in enumerate(all_candidates):
        title = cand.title
        family = cand.family
        params = cand.parameters
        chemistry = params.get("chemistry")

        # Derive basic ECM metrics from params (sidecar needs these for concordance)
        ecm_metrics = {
            "discharge_capacity": params.get("capacity_ah", 3.0),
            "coulombic_efficiency": params.get("coulombic_eff", 0.995),
            "internal_resistance": params.get("R0_mohm", 30) / 1000,  # Convert to Ohm
        }

        print(f"  [{i+1}/{len(all_candidates)}] {title} ({family}, chem={chemistry}) ... ", end="", flush=True)
        t0 = time.time()
        try:
            result = sidecar.verify_candidate(
                candidate_id=title,
                ecm_params=params,
                ecm_metrics=ecm_metrics,
                chemistry=chemistry,
            )
            elapsed = time.time() - t0
            results.append({
                "candidate_id": title,
                "family": family,
                "chemistry": chemistry,
                "seed": test_seed,
                "status": result.status.value,
                "concordance": result.concordance_score,
                "success": result.success,
                "timed_out": result.timed_out,
                "duration_s": round(elapsed, 2),
                "pybamm_parameter_set": result.pybamm_parameter_set,
                "concordance_details": result.concordance_details,
                "error_message": result.error_message,
                "gate_decision": _gate_decision(result),
            })
            print(f"{result.status.value} conc={result.concordance_score:.3f} gate={_gate_decision(result)} [{elapsed:.1f}s]")
        except Exception as e:
            elapsed = time.time() - t0
            errors.append({"candidate_id": title, "family": family, "error": str(e)})
            print(f"ERROR: {e} [{elapsed:.1f}s]")

    # Analyze
    analysis = analyze_sidecar_results(results)

    out_dir = Path("runtime/evaluation")
    out_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "checkpoint": "pybamm_sidecar_stability",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "health": health,
        "total_candidates": len(all_candidates),
        "total_verified": len(results),
        "total_errors": len(errors),
        "results": results,
        "analysis": analysis,
        "errors_detail": errors,
    }

    out_path = out_dir / "sidecar_stability_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved: {out_path}")

    return output


def _gate_decision(result):
    if not result.success:
        return "not_verified"
    if result.concordance_score >= CONCORDANCE_CONFIRM_THRESHOLD:
        return "confirmed"
    elif result.concordance_score >= CONCORDANCE_VETO_THRESHOLD:
        return "caveat"
    else:
        return "veto"


def analyze_sidecar_results(results):
    succeeded = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] != "success"]
    timed_out = [r for r in results if r["timed_out"]]

    concordances = [r["concordance"] for r in succeeded]
    durations = [r["duration_s"] for r in results]

    gate_counts = Counter(r["gate_decision"] for r in results)

    # By family
    family_stats = {}
    for family in set(r["family"] for r in results):
        fam_results = [r for r in results if r["family"] == family]
        fam_succeeded = [r for r in fam_results if r["status"] == "success"]
        fam_conc = [r["concordance"] for r in fam_succeeded]
        family_stats[family] = {
            "total": len(fam_results),
            "succeeded": len(fam_succeeded),
            "failed": len(fam_results) - len(fam_succeeded),
            "mean_concordance": round(sum(fam_conc) / len(fam_conc), 4) if fam_conc else 0,
            "min_concordance": round(min(fam_conc), 4) if fam_conc else 0,
            "max_concordance": round(max(fam_conc), 4) if fam_conc else 0,
            "gate_distribution": dict(Counter(r["gate_decision"] for r in fam_results)),
        }

    # By chemistry
    chem_stats = {}
    for chem in set(r["chemistry"] for r in results if r["chemistry"]):
        chem_results = [r for r in results if r["chemistry"] == chem]
        chem_succeeded = [r for r in chem_results if r["status"] == "success"]
        chem_conc = [r["concordance"] for r in chem_succeeded]
        chem_stats[chem] = {
            "total": len(chem_results),
            "succeeded": len(chem_succeeded),
            "mean_concordance": round(sum(chem_conc) / len(chem_conc), 4) if chem_conc else 0,
            "gate_distribution": dict(Counter(r["gate_decision"] for r in chem_results)),
        }

    return {
        "total": len(results),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "timed_out": len(timed_out),
        "success_rate": round(len(succeeded) / max(len(results), 1), 3),
        "concordance_stats": {
            "min": round(min(concordances), 4) if concordances else 0,
            "max": round(max(concordances), 4) if concordances else 0,
            "mean": round(sum(concordances) / len(concordances), 4) if concordances else 0,
        },
        "duration_stats": {
            "min": round(min(durations), 2) if durations else 0,
            "max": round(max(durations), 2) if durations else 0,
            "mean": round(sum(durations) / len(durations), 2) if durations else 0,
        },
        "gate_distribution": dict(gate_counts),
        "family_stats": family_stats,
        "chemistry_stats": chem_stats,
    }


if __name__ == "__main__":
    run_sidecar_stability()
