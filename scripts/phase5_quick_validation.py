#!/usr/bin/env python3
"""Quick Phase 5 validation: 3 cross-domain synthesis runs with increased timeout."""

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
logger = logging.getLogger("phase5_quick")

from breakthrough_engine.config_loader import load_program
from breakthrough_engine.candidate_generator import OllamaConfig
from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.embeddings import OllamaEmbeddingProvider
from breakthrough_engine.orchestrator import BreakthroughOrchestrator


def run_quick_validation():
    db_path = os.path.join("runtime", "db", "scires.db")
    db = init_db(db_path=db_path)
    repo = Repository(db)

    try:
        emb_provider = OllamaEmbeddingProvider()
    except Exception:
        from breakthrough_engine.embeddings import MockEmbeddingProvider
        emb_provider = MockEmbeddingProvider()

    results = []
    configs = ["cross_domain_shadow", "cross_domain_shadow", "cross_domain_review"]

    for i, config_name in enumerate(configs):
        logger.info("=" * 60)
        logger.info("Run %d/%d: %s", i + 1, len(configs), config_name)

        try:
            program = load_program(config_name)
            # Use increased timeout for synthesis runs
            from breakthrough_engine.candidate_generator import OllamaCandidateGenerator
            gen = OllamaCandidateGenerator(OllamaConfig.from_env())
            gen.config.timeout_seconds = 600  # 10 minutes for synthesis

            orch = BreakthroughOrchestrator(
                program=program,
                repo=repo,
                embedding_provider=emb_provider,
                generator=gen,
            )

            t0 = time.time()
            run = orch.run()
            duration = time.time() - t0

            metrics = repo.get_run_metrics(run.id)
            synthesis_ctx = repo.get_synthesis_context(run.id)
            emb_monitor = repo.get_embedding_monitor(run.id)
            candidates = repo.list_candidates_for_run(run.id)

            status_counts = {}
            for c in candidates:
                status_counts[c["status"]] = status_counts.get(c["status"], 0) + 1

            synthesis_fits = []
            for c in candidates:
                fit = repo.get_synthesis_fit(c["id"])
                if fit:
                    synthesis_fits.append(fit)

            max_sim = emb_monitor.get("max_similarity", 0) if emb_monitor else 0
            blocked = emb_monitor.get("blocked_count", 0) if emb_monitor else 0
            evaluated = emb_monitor.get("candidates_evaluated", 0) if emb_monitor else 0

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
                "bridge": synthesis_ctx.get("bridge_mechanism", "") if synthesis_ctx else "",
                "primary_sub": synthesis_ctx.get("primary_sub_domain", "") if synthesis_ctx else "",
                "secondary_sub": synthesis_ctx.get("secondary_sub_domain", "") if synthesis_ctx else "",
                "synthesis_fit_passed": sum(1 for f in synthesis_fits if f.get("passed")),
                "synthesis_fit_total": len(synthesis_fits),
                "draft": bool(metrics and metrics.get("draft_created")),
            }
            results.append(result)

            logger.info(
                "RESULT: gen=%d blocked=%d max_sim=%.3f bridge=%s fit=%d/%d dur=%.0fs",
                run.candidates_generated, blocked, max_sim,
                result["bridge"][:30], result["synthesis_fit_passed"],
                result["synthesis_fit_total"], duration,
            )

        except Exception as e:
            logger.error("Run failed: %s", e, exc_info=True)
            results.append({"config": config_name, "status": "FAILED", "error": str(e)})

    # Summary
    print("\n" + "=" * 80)
    print("PHASE 5 QUICK VALIDATION")
    print("=" * 80)
    for r in results:
        print(f"\n{r.get('run_id', 'N/A')[:8]} | {r.get('config')} | {r.get('status')}")
        if "error" not in r:
            print(f"  Gen={r['candidates_generated']} Blocked={r['embedding_blocked']} "
                  f"MaxSim={r['max_similarity']:.3f} Fit={r['synthesis_fit_passed']}/{r['synthesis_fit_total']} "
                  f"Draft={'Y' if r.get('draft') else 'N'} {r['duration_s']:.0f}s")
            print(f"  Bridge: {r.get('bridge', 'N/A')}")
            print(f"  Statuses: {r.get('status_counts', {})}")

    output = Path("runtime/breakthrough_reports/phase5_quick_validation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {output}")
    return results


if __name__ == "__main__":
    run_quick_validation()
