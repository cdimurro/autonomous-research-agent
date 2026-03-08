#!/usr/bin/env python3
"""Phase 5 live validation: Cross-domain synthesis runs.

Runs production_shadow and production_review cross-domain synthesis cycles
using real Ollama models, then reports results.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("phase5_validation")

from breakthrough_engine.config_loader import load_program
from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.embeddings import OllamaEmbeddingProvider
from breakthrough_engine.orchestrator import BreakthroughOrchestrator


def run_validation():
    # Use a separate DB for validation
    db_path = os.path.join("runtime", "db", "scires.db")
    db = init_db(db_path=db_path)
    repo = Repository(db)

    # Set up Ollama embedding provider
    try:
        emb_provider = OllamaEmbeddingProvider()
        logger.info("Using OllamaEmbeddingProvider (nomic-embed-text)")
    except Exception as e:
        logger.warning("Could not init OllamaEmbeddingProvider: %s", e)
        from breakthrough_engine.embeddings import MockEmbeddingProvider
        emb_provider = MockEmbeddingProvider()

    results = []

    # Run cross-domain shadow runs
    shadow_configs = ["cross_domain_shadow"] * 4
    review_configs = ["cross_domain_review"] * 2

    all_configs = shadow_configs + review_configs

    for i, config_name in enumerate(all_configs):
        logger.info("=" * 60)
        logger.info("Run %d/%d: %s", i + 1, len(all_configs), config_name)
        logger.info("=" * 60)

        try:
            program = load_program(config_name)
            orch = BreakthroughOrchestrator(
                program=program,
                repo=repo,
                embedding_provider=emb_provider,
            )

            t0 = time.time()
            run = orch.run()
            duration = time.time() - t0

            # Collect metrics
            metrics = repo.get_run_metrics(run.id)
            calibration = repo.get_calibration_diagnostic(run.id)
            synthesis_ctx = repo.get_synthesis_context(run.id)

            # Count candidates by status
            candidates = repo.list_candidates_for_run(run.id)
            status_counts = {}
            for c in candidates:
                status_counts[c["status"]] = status_counts.get(c["status"], 0) + 1

            # Get embedding stats
            emb_monitor = repo.get_embedding_monitor(run.id)
            max_sim = emb_monitor.get("max_similarity", 0) if emb_monitor else 0
            blocked = emb_monitor.get("blocked_count", 0) if emb_monitor else 0
            evaluated = emb_monitor.get("candidates_evaluated", 0) if emb_monitor else 0

            # Get synthesis fit data
            synthesis_fits = []
            for c in candidates:
                fit = repo.get_synthesis_fit(c["id"])
                if fit:
                    synthesis_fits.append(fit)

            result = {
                "run_id": run.id,
                "config": config_name,
                "status": run.status.value,
                "candidates_generated": run.candidates_generated,
                "duration_s": round(duration, 1),
                "status_counts": status_counts,
                "embedding_evaluated": evaluated,
                "embedding_blocked": blocked,
                "max_similarity": round(max_sim, 3),
                "synthesis_bridge": synthesis_ctx.get("bridge_mechanism", "") if synthesis_ctx else "",
                "synthesis_primary_sub": synthesis_ctx.get("primary_sub_domain", "") if synthesis_ctx else "",
                "synthesis_secondary_sub": synthesis_ctx.get("secondary_sub_domain", "") if synthesis_ctx else "",
                "synthesis_fit_count": len(synthesis_fits),
                "synthesis_fit_passed": sum(1 for f in synthesis_fits if f.get("passed")),
                "draft_created": bool(metrics and metrics.get("draft_created")),
            }
            results.append(result)

            logger.info(
                "Run %s completed: status=%s gen=%d blocked=%d max_sim=%.3f bridge=%s duration=%.1fs",
                run.id[:8], run.status.value, run.candidates_generated,
                blocked, max_sim,
                result["synthesis_bridge"][:40],
                duration,
            )

        except Exception as e:
            logger.error("Run %d failed: %s", i + 1, e, exc_info=True)
            results.append({
                "run_id": "",
                "config": config_name,
                "status": "FAILED",
                "error": str(e),
            })

    # Print summary
    print("\n" + "=" * 80)
    print("PHASE 5 LIVE VALIDATION SUMMARY")
    print("=" * 80)

    for r in results:
        print(f"\nRun: {r.get('run_id', 'N/A')[:8]}")
        print(f"  Config: {r.get('config')}")
        print(f"  Status: {r.get('status')}")
        if "error" in r:
            print(f"  Error: {r['error']}")
            continue
        print(f"  Candidates: {r.get('candidates_generated', 0)}")
        print(f"  Embedding: {r.get('embedding_evaluated', 0)} eval, {r.get('embedding_blocked', 0)} blocked, max_sim={r.get('max_similarity', 0):.3f}")
        print(f"  Bridge: {r.get('synthesis_bridge', 'N/A')}")
        print(f"  Sub-domains: {r.get('synthesis_primary_sub', '')} + {r.get('synthesis_secondary_sub', '')}")
        print(f"  Synthesis fit: {r.get('synthesis_fit_passed', 0)}/{r.get('synthesis_fit_count', 0)} passed")
        print(f"  Draft: {'Yes' if r.get('draft_created') else 'No'}")
        print(f"  Duration: {r.get('duration_s', 0):.1f}s")
        print(f"  Status counts: {r.get('status_counts', {})}")

    # Save results
    output_path = Path("runtime/breakthrough_reports/phase5_validation.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")

    return results


if __name__ == "__main__":
    run_validation()
