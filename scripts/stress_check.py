#!/usr/bin/env python3
"""Bounded stress check for Breakthrough Engine Phase 4D/5.

Estimates corpus growth effects, block-rate trends, and archive behavior
without requiring a full multi-day campaign.

Usage:
    python scripts/stress_check.py [--corpus-sizes 50,100,200,500] [--domain clean-energy]

This script:
1. Creates a temporary in-memory DB
2. Seeds it with synthetic candidates at various corpus sizes
3. Runs novelty evaluation at each size
4. Reports block-rate trends and archive behavior
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateStatus,
    EvidenceItem,
    RunMode,
    RunRecord,
    RunStatus,
    new_id,
)
from breakthrough_engine.novelty import NoveltyEngine
from breakthrough_engine.embeddings import EmbeddingNoveltyEngine, MockEmbeddingProvider
from breakthrough_engine.corpus_manager import CorpusManager


# Synthetic candidate templates for different sub-domains
TEMPLATES = [
    ("Solar {adj} {noun} for photovoltaic efficiency",
     "A novel {adj} {noun} enhances solar cell performance via {mechanism}.",
     "{noun}-based {mechanism} at the photovoltaic interface"),
    ("Grid-scale {noun} storage using {adj} architecture",
     "Deploying {adj} {noun} in grid storage enables {mechanism}.",
     "Reversible {mechanism} in {adj} {noun} systems"),
    ("Hydrogen production via {adj} {noun} electrolysis",
     "Combining {adj} catalysts with {noun} membranes improves HER via {mechanism}.",
     "{adj} {noun} catalysis reduces overpotential through {mechanism}"),
    ("{adj} {noun} for thermal energy management",
     "Phase-change {noun} with {adj} properties enables {mechanism} thermal storage.",
     "{mechanism} in {adj} {noun} composites"),
    ("Carbon capture using {adj} {noun} sorbents",
     "{adj} {noun} sorbents enable {mechanism} for direct air capture.",
     "Regenerable {mechanism} in {adj} {noun} materials"),
]

ADJECTIVES = [
    "nanostructured", "hierarchical", "bio-inspired", "self-healing",
    "two-dimensional", "topological", "amorphous", "crystalline",
    "porous", "layered", "doped", "functionalized", "gradient",
    "core-shell", "hollow", "defect-engineered", "strain-tuned",
    "interface-optimized", "quantum-confined", "metastable",
]

NOUNS = [
    "perovskite", "graphene", "MOF", "zeolite", "polymer",
    "alloy", "oxide", "nitride", "carbide", "sulfide",
    "silicene", "MXene", "borophene", "hydrogel", "aerogel",
    "nanofiber", "quantum dot", "nanotube", "nanosheet", "dendrimer",
]

MECHANISMS = [
    "phonon scattering", "charge transfer", "surface plasmon resonance",
    "defect migration", "spin-orbit coupling", "band alignment",
    "proton conductivity", "electron tunneling", "exciton dissociation",
    "ion intercalation", "catalytic cycling", "redox mediation",
    "photon upconversion", "thermal rectification", "mass transport",
]


def generate_synthetic_candidate(index: int, domain: str, run_id: str) -> CandidateHypothesis:
    """Generate a deterministic synthetic candidate from index."""
    template = TEMPLATES[index % len(TEMPLATES)]
    adj = ADJECTIVES[index % len(ADJECTIVES)]
    noun = NOUNS[(index * 7) % len(NOUNS)]
    mech = MECHANISMS[(index * 3) % len(MECHANISMS)]

    title = template[0].format(adj=adj, noun=noun, mechanism=mech)
    statement = template[1].format(adj=adj, noun=noun, mechanism=mech)
    mechanism = template[2].format(adj=adj, noun=noun, mechanism=mech)

    return CandidateHypothesis(
        id=hashlib.md5(f"{index}_{domain}".encode()).hexdigest()[:16],
        run_id=run_id,
        title=title[:200],
        domain=domain,
        statement=statement,
        mechanism=mechanism,
        expected_outcome="Measurable improvement in target metric.",
        assumptions=[f"Assumption for candidate {index}"],
        risk_flags=[],
        evidence_refs=[],
        status=CandidateStatus.GENERATED,
    )


def run_stress_check(
    corpus_sizes: list[int],
    domain: str = "clean-energy",
    archive_threshold_days: int = 30,
) -> list[dict]:
    """Run stress check at various corpus sizes."""
    results = []

    for target_size in corpus_sizes:
        db = init_db(in_memory=True)
        repo = Repository(db)
        novelty_engine = NoveltyEngine(db)
        emb_engine = EmbeddingNoveltyEngine(provider=MockEmbeddingProvider())
        corpus_manager = CorpusManager(repo)

        # Create a run for the seeded candidates
        seed_run_id = new_id()
        seed_run = RunRecord(
            id=seed_run_id,
            program_name="stress_check_seed",
            mode=RunMode.DEMO_LOCAL,
            status=RunStatus.COMPLETED,
        )
        repo.save_run(seed_run)

        # Seed corpus
        t0 = time.time()
        for i in range(target_size):
            c = generate_synthetic_candidate(i, domain, seed_run_id)
            repo.save_candidate(c)
        seed_time = time.time() - t0

        # Create test run
        test_run_id = new_id()
        test_run = RunRecord(
            id=test_run_id,
            program_name="stress_check_test",
            mode=RunMode.DEMO_LOCAL,
            status=RunStatus.STARTED,
        )
        repo.save_run(test_run)

        # Generate 10 new test candidates and check novelty
        test_candidates = [
            generate_synthetic_candidate(target_size + i, domain, test_run_id)
            for i in range(10)
        ]

        blocked_lexical = 0
        blocked_embedding = 0
        t0 = time.time()

        # Build prior texts for embedding
        prior_cands = novelty_engine._get_prior_candidates(domain, test_run_id)
        prior_texts = [
            {
                "title": pc.get("title", ""),
                "text": f"{pc.get('title', '')}. {pc.get('statement', '')}",
                "source": "local_candidate",
                "source_id": pc.get("id", ""),
            }
            for pc in prior_cands
        ]

        for c in test_candidates:
            result = novelty_engine.evaluate(c, exclude_run_id=test_run_id)
            if result.decision.value == "fail":
                blocked_lexical += 1

            emb_result = emb_engine.evaluate(c, prior_texts=prior_texts)
            if emb_result.blocked_by_prior_art:
                blocked_embedding += 1

        eval_time = time.time() - t0

        # Check archive behavior
        archive_stats = corpus_manager.run_archival(domain)
        active_count = corpus_manager.get_active_count(domain)

        result = {
            "corpus_size": target_size,
            "domain": domain,
            "seed_time_s": round(seed_time, 3),
            "eval_time_s": round(eval_time, 3),
            "test_candidates": 10,
            "lexical_blocked": blocked_lexical,
            "embedding_blocked": blocked_embedding,
            "lexical_block_rate": f"{blocked_lexical / 10 * 100:.0f}%",
            "embedding_block_rate": f"{blocked_embedding / 10 * 100:.0f}%",
            "archived_by_age": archive_stats.get("archived_by_age", 0),
            "active_corpus": active_count,
        }
        results.append(result)

        db.close()

    return results


def main():
    parser = argparse.ArgumentParser(description="Breakthrough Engine stress check")
    parser.add_argument(
        "--corpus-sizes",
        default="50,100,200,500",
        help="Comma-separated corpus sizes to test (default: 50,100,200,500)",
    )
    parser.add_argument(
        "--domain",
        default="clean-energy",
        help="Domain to test (default: clean-energy)",
    )
    args = parser.parse_args()

    sizes = [int(s.strip()) for s in args.corpus_sizes.split(",")]
    print(f"Stress check: domain={args.domain}, sizes={sizes}")
    print("=" * 70)

    results = run_stress_check(sizes, domain=args.domain)

    # Print results table
    print(f"\n{'Size':>6} | {'Seed(s)':>8} | {'Eval(s)':>8} | {'Lex Block':>10} | {'Emb Block':>10} | {'Active':>8}")
    print("-" * 70)
    for r in results:
        print(
            f"{r['corpus_size']:>6} | "
            f"{r['seed_time_s']:>8.3f} | "
            f"{r['eval_time_s']:>8.3f} | "
            f"{r['lexical_block_rate']:>10} | "
            f"{r['embedding_block_rate']:>10} | "
            f"{r['active_corpus']:>8}"
        )

    print("\n" + json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    main()
