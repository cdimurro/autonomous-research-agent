#!/usr/bin/env python3
"""Battery decision-brief generation campaign for evaluation.

Runs battery benchmarks across a spread of seeds and modes,
generates decision briefs, and collects campaign-level statistics.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/eval_battery_campaign.py
"""

import json
import sys
import time
from collections import Counter
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from breakthrough_engine.battery_loop import run_battery_benchmark
from breakthrough_engine.battery_decision_brief import (
    generate_decision_brief,
    save_decision_brief,
)
from breakthrough_engine.battery_sidecar import MockPyBaMMSidecar
from breakthrough_engine.db import Repository, init_db


# --- Campaign configuration ---
# Seeds spread across a range for diversity
SEEDS_ECM_ONLY = list(range(100, 118))        # 18 seeds, no sidecar
SEEDS_MOCK_SIDECAR = list(range(200, 218))     # 18 seeds, mock sidecar
SEEDS_CATHODE_MOCK = list(range(300, 310))     # 10 seeds, 8 candidates (cathode-heavy), mock sidecar

N_CANDIDATES_STANDARD = 6
N_CANDIDATES_CATHODE = 8


def run_campaign():
    db = init_db()
    repo = Repository(db)
    results = []
    briefs = []
    errors = []

    configs = []
    for s in SEEDS_ECM_ONLY:
        configs.append({"seed": s, "n_candidates": N_CANDIDATES_STANDARD, "mode": "ecm_only", "sidecar": None})
    for s in SEEDS_MOCK_SIDECAR:
        configs.append({"seed": s, "n_candidates": N_CANDIDATES_STANDARD, "mode": "ecm_mock_sidecar", "sidecar": "mock"})
    for s in SEEDS_CATHODE_MOCK:
        configs.append({"seed": s, "n_candidates": N_CANDIDATES_CATHODE, "mode": "cathode_mock", "sidecar": "mock"})

    total = len(configs)
    print(f"=== Battery Decision-Brief Campaign ===")
    print(f"Total runs planned: {total}")
    print(f"  ECM-only:       {len(SEEDS_ECM_ONLY)}")
    print(f"  Mock sidecar:   {len(SEEDS_MOCK_SIDECAR)}")
    print(f"  Cathode+mock:   {len(SEEDS_CATHODE_MOCK)}")
    print()

    for i, cfg in enumerate(configs):
        seed = cfg["seed"]
        mode = cfg["mode"]
        n_cand = cfg["n_candidates"]
        print(f"[{i+1}/{total}] seed={seed} mode={mode} n={n_cand} ... ", end="", flush=True)
        t0 = time.time()
        try:
            # Resolve sidecar
            sidecar = None
            if cfg["sidecar"] == "mock":
                sidecar = MockPyBaMMSidecar(seed=seed)

            report = run_battery_benchmark(
                repo=repo,
                n_candidates=n_cand,
                seed=seed,
                sidecar=sidecar,
            )
            elapsed = time.time() - t0

            # Try generating a brief
            brief = generate_decision_brief(report)
            brief_id = None
            if brief:
                path = save_decision_brief(brief)
                brief_id = brief.id
                briefs.append(brief.model_dump())

            # Collect run result
            summary = report.get("summary", {})
            best = report.get("best_candidate", {})
            sidecar_v = report.get("sidecar_verification", {})

            results.append({
                "seed": seed,
                "mode": mode,
                "n_candidates": n_cand,
                "elapsed_s": round(elapsed, 2),
                "promoted": summary.get("promoted_count", 0),
                "rejected": summary.get("rejected_count", 0),
                "hard_fail": summary.get("hard_fail_count", 0),
                "best_score": best.get("score", 0),
                "best_family": best.get("family", "none"),
                "promotion_decision": report.get("promotion_decision", "none"),
                "sidecar_status": sidecar_v.get("status", "not_verified"),
                "sidecar_concordance": sidecar_v.get("concordance_score"),
                "sidecar_gate": (sidecar_v.get("gate_decision") or "not_verified") if sidecar_v else "not_verified",
                "brief_id": brief_id,
                "caveats": report.get("caveats", []),
                "reference_envelope": report.get("reference_comparison", {}).get("within_reference_envelope"),
            })
            status = "PROMOTED" if brief_id else "no-promotion"
            print(f"{status} score={best.get('score', 0):.3f} family={best.get('family', '?')} [{elapsed:.1f}s]")

        except Exception as e:
            elapsed = time.time() - t0
            errors.append({"seed": seed, "mode": mode, "error": str(e)})
            print(f"ERROR: {e} [{elapsed:.1f}s]")

    # --- Analyze results ---
    print(f"\n=== Campaign Complete ===")
    print(f"Runs: {len(results)} success, {len(errors)} errors")
    print(f"Briefs generated: {len(briefs)}")

    analysis = analyze_campaign(results, briefs)

    # Save raw results
    out_dir = Path("runtime/evaluation")
    out_dir.mkdir(parents=True, exist_ok=True)

    campaign_data = {
        "campaign": "battery_decision_brief_density",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_runs": len(configs),
        "successful_runs": len(results),
        "errors": len(errors),
        "briefs_generated": len(briefs),
        "results": results,
        "briefs_summary": [
            {
                "id": b["id"],
                "family": b["candidate_family"],
                "chemistry": b.get("chemistry"),
                "score": b["final_score"],
                "confidence_tier": b["confidence_tier"],
                "sidecar_gate": b["sidecar_gate_decision"],
                "headline": b["headline"],
                "why_promising": b["why_promising"],
                "recommended_action": b["recommended_action"],
                "caveats": b["caveats"],
            }
            for b in briefs
        ],
        "analysis": analysis,
        "errors_detail": errors,
    }

    out_path = out_dir / "battery_campaign_results.json"
    with open(out_path, "w") as f:
        json.dump(campaign_data, f, indent=2, default=str)
    print(f"\nResults saved: {out_path}")

    return campaign_data


def analyze_campaign(results, briefs):
    """Compute campaign-level statistics."""
    promoted = [r for r in results if r["promotion_decision"] == "promoted"]
    families = Counter(r["best_family"] for r in promoted)
    scores = [r["best_score"] for r in promoted]

    # Brief-level analysis
    brief_families = Counter(b["candidate_family"] for b in briefs)
    confidence_tiers = Counter(b["confidence_tier"] for b in briefs)
    sidecar_gates = Counter(b["sidecar_gate_decision"] for b in briefs)

    # Caveat patterns
    all_caveats = []
    for b in briefs:
        all_caveats.extend(b.get("caveats", []))
    caveat_counter = Counter(all_caveats)

    # Why-promising patterns
    why_patterns = Counter(b["why_promising"] for b in briefs)

    # Recommended action patterns
    action_patterns = Counter(b["recommended_action"] for b in briefs)

    # Headline uniqueness
    headlines = [b["headline"] for b in briefs]
    unique_headlines = len(set(headlines))

    # Score distribution
    brief_scores = [b["final_score"] for b in briefs]

    # Mode breakdown
    mode_stats = {}
    for mode in ["ecm_only", "ecm_mock_sidecar", "cathode_mock"]:
        mode_runs = [r for r in results if r["mode"] == mode]
        mode_promoted = [r for r in mode_runs if r["promotion_decision"] == "promoted"]
        mode_stats[mode] = {
            "runs": len(mode_runs),
            "promoted": len(mode_promoted),
            "promotion_rate": round(len(mode_promoted) / max(len(mode_runs), 1), 3),
            "families": dict(Counter(r["best_family"] for r in mode_promoted)),
            "mean_score": round(sum(r["best_score"] for r in mode_promoted) / max(len(mode_promoted), 1), 4) if mode_promoted else 0,
        }

    return {
        "total_promoted": len(promoted),
        "promotion_rate": round(len(promoted) / max(len(results), 1), 3),
        "family_distribution": dict(families),
        "score_stats": {
            "min": round(min(scores), 4) if scores else 0,
            "max": round(max(scores), 4) if scores else 0,
            "mean": round(sum(scores) / len(scores), 4) if scores else 0,
        },
        "brief_count": len(briefs),
        "unique_headlines": unique_headlines,
        "headline_uniqueness_ratio": round(unique_headlines / max(len(briefs), 1), 3),
        "confidence_tiers": dict(confidence_tiers),
        "sidecar_gate_distribution": dict(sidecar_gates),
        "brief_family_distribution": dict(brief_families),
        "top_caveats": dict(caveat_counter.most_common(10)),
        "why_promising_patterns": dict(why_patterns.most_common(10)),
        "recommended_action_patterns": dict(action_patterns),
        "brief_score_stats": {
            "min": round(min(brief_scores), 4) if brief_scores else 0,
            "max": round(max(brief_scores), 4) if brief_scores else 0,
            "mean": round(sum(brief_scores) / len(brief_scores), 4) if brief_scores else 0,
        },
        "mode_breakdown": mode_stats,
    }


if __name__ == "__main__":
    run_campaign()
