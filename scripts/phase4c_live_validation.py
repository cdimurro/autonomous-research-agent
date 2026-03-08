#!/usr/bin/env python3
"""Phase 4C: Live validation of real Ollama embeddings over multiple runs.

Runs production_shadow and production_review cycles with real Ollama
generation and embedding models. Records detailed per-run metrics.
"""

import json
import os
import sys
import time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.config_loader import load_program
from breakthrough_engine.embeddings import OllamaEmbeddingProvider
from breakthrough_engine.models import RunMode, ResearchProgram
from breakthrough_engine.orchestrator import BreakthroughOrchestrator


def run_validation(
    num_shadow: int = 5,
    num_review: int = 2,
    domain: str = "clean-energy",
    db_path: str = "runtime/db/scires.db",
):
    """Run live validation cycles and collect results."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = init_db(db_path=db_path)
    repo = Repository(db)

    # Check Ollama availability
    emb_provider = OllamaEmbeddingProvider()
    if not emb_provider.is_available():
        print("[ERROR] Ollama embedding model not available. Pull nomic-embed-text first.")
        return

    print(f"[INFO] Embedding model: {emb_provider.model}, dim: {emb_provider.dimension()}")
    print(f"[INFO] Generation model: qwen3.5:9b-q4_K_M")
    print(f"[INFO] Domain: {domain}")
    print(f"[INFO] Shadow runs: {num_shadow}, Review runs: {num_review}")
    print("=" * 60)

    results = []

    # Shadow runs
    for i in range(num_shadow):
        print(f"\n[RUN {i+1}/{num_shadow}] production_shadow")
        program = ResearchProgram(
            name=f"validation_shadow_{i}",
            domain=domain,
            goal="Discover novel materials and processes for renewable energy generation and storage.",
            candidate_budget=5,
            simulation_budget=2,
            publication_threshold=0.60,
            mode=RunMode.PRODUCTION_SHADOW,
        )

        t0 = time.time()
        try:
            orch = BreakthroughOrchestrator(
                program=program, repo=repo,
                embedding_provider=emb_provider,
            )
            run = orch.run()
            duration = round(time.time() - t0, 1)

            # Collect metrics
            metrics = repo.get_run_metrics(run.id)
            monitor = repo.get_embedding_monitor(run.id)
            cal = repo.get_calibration_diagnostic(run.id)
            candidates = repo.list_candidates_for_run(run.id)

            status_counts = {}
            for c in candidates:
                s = c.get("status", "unknown")
                status_counts[s] = status_counts.get(s, 0) + 1

            result = {
                "run_id": run.id,
                "mode": "production_shadow",
                "gen_model": "qwen3.5:9b-q4_K_M",
                "emb_model": "nomic-embed-text",
                "duration_s": duration,
                "candidates_generated": run.candidates_generated,
                "status_counts": status_counts,
                "publication_id": run.publication_id,
                "run_status": run.status.value,
            }

            if monitor:
                result["emb_max_sim"] = monitor.get("max_similarity", 0)
                result["emb_mean_sim"] = monitor.get("mean_similarity", 0)
                result["emb_blocked"] = monitor.get("blocked_count", 0)
                result["emb_warned"] = monitor.get("warned_count", 0)
                result["emb_evaluated"] = monitor.get("candidates_evaluated", 0)

            if cal:
                result["domain_fit_mean"] = cal.get("domain_fit_mean_score", 0)
                result["domain_fit_fail"] = cal.get("domain_fit_fail_count", 0)
                result["pub_pass"] = cal.get("publication_pass_count", 0)
                result["pub_fail"] = cal.get("publication_fail_count", 0)

            results.append(result)
            print(f"  Status: {run.status.value} | Candidates: {run.candidates_generated} | Duration: {duration}s")
            if monitor:
                print(f"  Embedding: max_sim={monitor.get('max_similarity', 0):.3f}, "
                      f"blocked={monitor.get('blocked_count', 0)}, warned={monitor.get('warned_count', 0)}")
            print(f"  Statuses: {status_counts}")

        except Exception as e:
            print(f"  [ERROR] Run failed: {e}")
            results.append({"run_id": "failed", "mode": "production_shadow", "error": str(e)})

    # Review runs
    for i in range(num_review):
        print(f"\n[RUN {num_shadow+i+1}/{num_shadow+num_review}] production_review")
        program = ResearchProgram(
            name=f"validation_review_{i}",
            domain=domain,
            goal="Discover novel materials and processes for renewable energy generation and storage.",
            candidate_budget=5,
            simulation_budget=2,
            publication_threshold=0.60,
            mode=RunMode.PRODUCTION_REVIEW,
        )

        t0 = time.time()
        try:
            orch = BreakthroughOrchestrator(
                program=program, repo=repo,
                embedding_provider=emb_provider,
            )
            run = orch.run()
            duration = round(time.time() - t0, 1)

            monitor = repo.get_embedding_monitor(run.id)
            cal = repo.get_calibration_diagnostic(run.id)
            draft = repo.get_draft_by_run(run.id)
            candidates = repo.list_candidates_for_run(run.id)

            status_counts = {}
            for c in candidates:
                s = c.get("status", "unknown")
                status_counts[s] = status_counts.get(s, 0) + 1

            result = {
                "run_id": run.id,
                "mode": "production_review",
                "gen_model": "qwen3.5:9b-q4_K_M",
                "emb_model": "nomic-embed-text",
                "duration_s": duration,
                "candidates_generated": run.candidates_generated,
                "status_counts": status_counts,
                "draft_created": draft is not None,
                "run_status": run.status.value,
            }

            if monitor:
                result["emb_max_sim"] = monitor.get("max_similarity", 0)
                result["emb_mean_sim"] = monitor.get("mean_similarity", 0)
                result["emb_blocked"] = monitor.get("blocked_count", 0)
                result["emb_warned"] = monitor.get("warned_count", 0)

            if cal:
                result["domain_fit_mean"] = cal.get("domain_fit_mean_score", 0)
                result["pub_pass"] = cal.get("publication_pass_count", 0)
                result["pub_fail"] = cal.get("publication_fail_count", 0)

            results.append(result)
            print(f"  Status: {run.status.value} | Candidates: {run.candidates_generated} | Duration: {duration}s")
            if monitor:
                print(f"  Embedding: max_sim={monitor.get('max_similarity', 0):.3f}, "
                      f"blocked={monitor.get('blocked_count', 0)}, warned={monitor.get('warned_count', 0)}")
            if draft:
                print(f"  Draft created: {draft['candidate_title'][:60]}")

        except Exception as e:
            print(f"  [ERROR] Run failed: {e}")
            results.append({"run_id": "failed", "mode": "production_review", "error": str(e)})

    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    total = len(results)
    errors = sum(1 for r in results if "error" in r)
    print(f"Total runs: {total}, Errors: {errors}")

    if results:
        avg_duration = sum(r.get("duration_s", 0) for r in results if "error" not in r) / max(1, total - errors)
        avg_candidates = sum(r.get("candidates_generated", 0) for r in results if "error" not in r) / max(1, total - errors)
        emb_blocks = sum(r.get("emb_blocked", 0) for r in results if "error" not in r)
        emb_warns = sum(r.get("emb_warned", 0) for r in results if "error" not in r)
        max_sims = [r.get("emb_max_sim", 0) for r in results if "error" not in r and "emb_max_sim" in r]

        print(f"Avg duration: {avg_duration:.1f}s")
        print(f"Avg candidates/run: {avg_candidates:.1f}")
        print(f"Total embedding blocks: {emb_blocks}")
        print(f"Total embedding warns: {emb_warns}")
        if max_sims:
            print(f"Max similarity range: {min(max_sims):.3f} - {max(max_sims):.3f}")

    # Save results
    output_path = "runtime/phase4c_validation_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {output_path}")

    # Get drift report
    from breakthrough_engine.embedding_monitor import EmbeddingMonitor
    monitor = EmbeddingMonitor(repo)
    drift = monitor.get_drift_report(limit=20)
    drift_path = "runtime/phase4c_drift_report.json"
    with open(drift_path, "w") as f:
        json.dump(drift, f, indent=2, default=str)
    print(f"Drift report saved to: {drift_path}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--shadow", type=int, default=5, help="Number of shadow runs")
    parser.add_argument("--review", type=int, default=2, help="Number of review runs")
    parser.add_argument("--domain", default="clean-energy")
    args = parser.parse_args()
    run_validation(num_shadow=args.shadow, num_review=args.review, domain=args.domain)
