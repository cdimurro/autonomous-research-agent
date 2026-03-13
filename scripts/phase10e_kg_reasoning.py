#!/usr/bin/env python
"""Phase 10E: KG Reasoning Upgrade — Retrieval Comparison V3.

Produces:
  - Multi-signal segment re-scoring
  - Extraction coverage stats
  - Graph reasoning path stats
  - Cross-paper synthesis stats
  - 3-way retrieval comparison (current / KG / upgraded hybrid)
  - Switch-readiness recommendation
  - All artifacts in runtime/phase10e/
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from breakthrough_engine.db import Repository
from breakthrough_engine.evidence_source import ExistingFindingsSource
from breakthrough_engine.hybrid_retrieval import HybridKGEvidenceSource
from breakthrough_engine.kg_calibration import EvidenceCalibrator
from breakthrough_engine.kg_comparison import RetrievalComparisonHarness
from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
from breakthrough_engine.kg_reasoning import (
    CrossPaperSynthesizer,
    KGGraphBuilder,
    MultiHopReasoner,
)
from breakthrough_engine.kg_retrieval import KGEvidenceSource
from breakthrough_engine.kg_segment_scorer import MultiSignalSegmentScorer

OUTDIR = os.path.join(ROOT, "runtime", "phase10e")
DB_PATH = os.path.join(ROOT, "runtime", "db", "scires.db")
DOMAIN = "clean-energy"
LIMIT = 30


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# A: Multi-signal segment re-scoring
# ---------------------------------------------------------------------------

def rescore_segments(db: sqlite3.Connection) -> dict:
    """Compute multi-signal scores for all segments (non-destructive).

    Uses the existing embedding-based relevance_score from the DB as the
    embedding_similarity signal, then layers keyword/quantitative/citation/
    mechanism signals on top via weighted composite.

    Does NOT overwrite the DB relevance_score — the embedding-based score
    is the canonical value used by retrieval. Multi-signal analysis is
    reported for diagnostics only.
    """
    scorer = MultiSignalSegmentScorer()
    rows = db.execute(
        "SELECT id, raw_text, compressed_text, relevance_score, domain FROM bt_paper_segments"
    ).fetchall()

    stats = {"total": len(rows), "analyzed": 0, "would_improve": 0, "would_degrade": 0}
    breakdowns = []

    for row in rows:
        seg_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
        text = (row["compressed_text"] if isinstance(row, sqlite3.Row) else row[2]) or \
               (row["raw_text"] if isinstance(row, sqlite3.Row) else row[1]) or ""
        embedding_score = float(row["relevance_score"] if isinstance(row, sqlite3.Row) else row[3] or 0.5)
        domain = (row["domain"] if isinstance(row, sqlite3.Row) else row[4]) or DOMAIN

        if not text or len(text.strip()) < 20:
            continue

        breakdown = scorer.score(text, domain, str(seg_id))
        # Use the actual embedding-based relevance_score from the DB
        breakdown.embedding_similarity = embedding_score
        # Recompute composite with the real embedding signal
        w = scorer.config.weights_dict()
        breakdown.composite_score = max(0.0, min(1.0, (
            breakdown.embedding_similarity * w["embedding_similarity"]
            + breakdown.keyword_overlap * w["keyword_overlap"]
            + breakdown.quantitative_density * w["quantitative_density"]
            + breakdown.citation_density * w["citation_density"]
            + breakdown.mechanism_specificity * w["mechanism_specificity"]
        )))
        composite = breakdown.composite_score

        stats["analyzed"] += 1
        if composite > embedding_score + 0.01:
            stats["would_improve"] += 1
        elif composite < embedding_score - 0.01:
            stats["would_degrade"] += 1

        breakdowns.append(breakdown.to_dict())

    # Score distributions
    embedding_scores = [b["embedding_similarity"] for b in breakdowns]
    composite_scores = [b["composite_score"] for b in breakdowns]
    if embedding_scores:
        embedding_scores.sort()
        n = len(embedding_scores)
        stats["embedding_mean"] = round(sum(embedding_scores) / n, 4)
        stats["embedding_median"] = round(embedding_scores[n // 2], 4)
    if composite_scores:
        composite_scores.sort()
        n = len(composite_scores)
        stats["composite_mean"] = round(sum(composite_scores) / n, 4)
        stats["composite_median"] = round(composite_scores[n // 2], 4)
        stats["composite_min"] = round(min(composite_scores), 4)
        stats["composite_max"] = round(max(composite_scores), 4)

    return stats


# ---------------------------------------------------------------------------
# B/C: Extraction and coverage stats
# ---------------------------------------------------------------------------

def extraction_stats(db: sqlite3.Connection) -> dict:
    """Gather extraction coverage and confidence stats."""
    total = db.execute("SELECT COUNT(*) FROM bt_paper_segments").fetchone()[0]
    extracted = db.execute("SELECT COUNT(*) FROM bt_paper_segments WHERE status='extracted'").fetchone()[0]
    scored = db.execute("SELECT COUNT(*) FROM bt_paper_segments WHERE status='scored'").fetchone()[0]
    entities = db.execute("SELECT COUNT(*) FROM bt_kg_entities").fetchone()[0]
    relations = db.execute("SELECT COUNT(*) FROM bt_kg_relations").fetchone()[0]

    # Confidence distributions
    ent_confs = [r[0] for r in db.execute("SELECT confidence FROM bt_kg_entities").fetchall()]
    rel_confs = [r[0] for r in db.execute("SELECT confidence FROM bt_kg_relations").fetchall()]

    stats = {
        "total_segments": total,
        "scored": scored,
        "extracted": extracted,
        "coverage_pct": round(extracted / total * 100, 1) if total else 0,
        "entities": entities,
        "relations": relations,
    }

    if ent_confs:
        stats["entity_confidence"] = {
            "mean": round(sum(ent_confs) / len(ent_confs), 3),
            "min": round(min(ent_confs), 3),
            "max": round(max(ent_confs), 3),
        }
    if rel_confs:
        stats["relation_confidence"] = {
            "mean": round(sum(rel_confs) / len(rel_confs), 3),
            "min": round(min(rel_confs), 3),
            "max": round(max(rel_confs), 3),
        }

    return stats


# ---------------------------------------------------------------------------
# D/E: Graph reasoning and synthesis stats
# ---------------------------------------------------------------------------

def graph_reasoning_stats(repo: Repository) -> dict:
    """Build graph, find reasoning paths and synthesis links."""
    graph = KGGraphBuilder(repo)
    graph.load(domain=DOMAIN, limit=500)

    stats = {
        "graph_nodes": graph.node_count,
        "graph_edges": graph.edge_count,
    }

    # Multi-hop paths
    reasoner = MultiHopReasoner(graph, max_hops=2, min_path_confidence=0.15)
    paths = reasoner.find_paths(domain=DOMAIN, limit=50)
    cross_paths = [p for p in paths if p.is_cross_paper]

    stats["paths_found"] = len(paths)
    stats["cross_paper_paths"] = len(cross_paths)
    if paths:
        stats["path_confidence_mean"] = round(sum(p.path_confidence for p in paths) / len(paths), 4)
        stats["path_hop_distribution"] = {}
        for p in paths:
            h = str(p.hop_count)
            stats["path_hop_distribution"][h] = stats["path_hop_distribution"].get(h, 0) + 1

    # Cross-paper synthesis
    synth = CrossPaperSynthesizer(graph, min_confidence=0.15)
    links = synth.synthesize(domain=DOMAIN, limit=20)
    stats["synthesis_links"] = len(links)
    if links:
        stats["synthesis_confidence_mean"] = round(sum(l.synthesis_confidence for l in links) / len(links), 4)

    # Convert to evidence items for later use
    path_evidence = reasoner.paths_to_evidence(paths[:10])
    synth_evidence = synth.synthesis_to_evidence(links[:5])

    stats["path_evidence_items"] = len(path_evidence)
    stats["synthesis_evidence_items"] = len(synth_evidence)

    return stats, path_evidence, synth_evidence


# ---------------------------------------------------------------------------
# I: Retrieval comparison v3
# ---------------------------------------------------------------------------

def run_retrieval_comparison_v3(
    repo: Repository, db: sqlite3.Connection,
    path_evidence: list, synth_evidence: list,
) -> dict:
    """3-way retrieval comparison after hardening."""
    from breakthrough_engine.evidence_source import EvidenceSource
    from breakthrough_engine.models import EvidenceItem

    current_source = ExistingFindingsSource(db, min_confidence=0.6)
    kg_source = KGEvidenceSource(repo, min_relevance=0.2)
    calibrator = EvidenceCalibrator()

    # Upgraded hybrid: includes graph paths and synthesis evidence
    class UpgradedHybridSource(EvidenceSource):
        def __init__(self, trusted, kg, path_ev, synth_ev, cal):
            self._hybrid = HybridKGEvidenceSource(
                trusted_source=trusted,
                kg_source=kg,
                min_trusted_quota=10,
                max_single_source_pct=0.35,
                kg_diversification_quota=12,
                calibrator=cal,
            )
            self._path_evidence = path_ev
            self._synth_evidence = synth_ev

        def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
            base = self._hybrid.gather(domain, limit=max(limit - 5, 10))
            # Add graph path and synthesis evidence
            extra = (self._path_evidence + self._synth_evidence)[:5]
            # Calibrate extra items
            if extra:
                calibrator.calibrate(extra)
            combined = base + extra
            combined.sort(key=lambda x: x.relevance_score, reverse=True)
            return combined[:limit]

    upgraded = UpgradedHybridSource(
        ExistingFindingsSource(db, min_confidence=0.6),
        KGEvidenceSource(repo, min_relevance=0.2),
        list(path_evidence), list(synth_evidence),
        calibrator,
    )

    harness = RetrievalComparisonHarness(
        current_source=current_source,
        shadow_source=kg_source,
        hybrid_source=upgraded,
    )

    result = harness.compare(domain=DOMAIN, limit=LIMIT)

    # Export
    outdir = ensure_dir(os.path.join(OUTDIR, "retrieval_comparison"))
    harness.export_json(result, os.path.join(outdir, "retrieval_comparison_v3.json"))
    harness.export_markdown(result, os.path.join(outdir, "retrieval_comparison_v3.md"))
    harness.export_csv(result, os.path.join(outdir, "retrieval_comparison_v3.csv"))

    # Export evidence CSVs
    for name, src_fn in [
        ("current", lambda: current_source.gather(DOMAIN, limit=LIMIT)),
        ("kg", lambda: kg_source.gather(DOMAIN, limit=LIMIT)),
        ("upgraded_hybrid", lambda: upgraded.gather(DOMAIN, limit=LIMIT)),
    ]:
        items = src_fn()
        path = os.path.join(outdir, f"evidence_items_{name}.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["source_type", "source_id", "title", "relevance_score", "quote_len"])
            for it in items:
                w.writerow([it.source_type, it.source_id, it.title[:80], round(it.relevance_score, 4), len(it.quote)])

    return result.to_dict()


# ---------------------------------------------------------------------------
# K: Switch readiness
# ---------------------------------------------------------------------------

def switch_readiness(comparison: dict) -> dict:
    """Produce switch-readiness recommendation."""
    decision: dict = {"timestamp": datetime.now(timezone.utc).isoformat()}

    current = comparison.get("current", {})
    hybrid = comparison.get("hybrid", {})

    if not hybrid:
        decision["recommendation"] = "keep_shadow_only"
        decision["reason"] = "Upgraded hybrid retrieval not tested."
        return decision

    current_rel = current.get("mean_relevance", 0)
    hybrid_rel = hybrid.get("mean_relevance", 0)
    hybrid_div = hybrid.get("unique_source_ids", 0)
    current_div = current.get("unique_source_ids", 0)

    checks = {}

    # Score preservation
    score_ok = hybrid_rel >= current_rel - 0.01
    checks["score_preservation"] = {
        "required": f">= {current_rel - 0.01:.4f}",
        "actual": f"{hybrid_rel:.4f}",
        "pass": score_ok,
    }

    # Diversity improvement
    div_ok = hybrid_div >= current_div
    checks["diversity_improvement"] = {
        "required": f">= {current_div}",
        "actual": str(hybrid_div),
        "pass": div_ok,
    }

    # Source type diversity
    hybrid_types = len(hybrid.get("source_type_counts", {}))
    current_types = len(current.get("source_type_counts", {}))
    type_ok = hybrid_types > current_types
    checks["source_type_diversity"] = {
        "required": f"> {current_types}",
        "actual": str(hybrid_types),
        "pass": type_ok,
    }

    all_pass = score_ok and (div_ok or type_ok)
    if all_pass:
        decision["recommendation"] = "ready_for_limited_production_retrieval_ab"
        decision["reason"] = (
            "Upgraded hybrid retrieval preserves score quality while adding "
            "graph-path and cross-paper synthesis evidence. "
            "Recommend a bounded production A/B trial."
        )
    else:
        decision["recommendation"] = "keep_shadow_only"
        failures = [k for k, v in checks.items() if not v["pass"]]
        decision["reason"] = f"Failed checks: {', '.join(failures)}"
        decision["fixes_needed"] = []
        if not score_ok:
            decision["fixes_needed"].append("Improve calibration to preserve score quality")
        if not div_ok and not type_ok:
            decision["fixes_needed"].append("Increase diversity contribution")

    decision["checks"] = checks
    return decision


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Phase 10E: KG Reasoning Upgrade Pipeline")
    print("=" * 60)

    ensure_dir(OUTDIR)

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    repo = Repository(db)

    # A: Multi-signal segment analysis (non-destructive — does NOT overwrite DB scores)
    print("\n[A] Multi-signal segment analysis...")
    score_stats = rescore_segments(db)
    with open(os.path.join(OUTDIR, "segment_rescoring.json"), "w") as f:
        json.dump(score_stats, f, indent=2)
    print(f"  Analyzed: {score_stats['analyzed']}/{score_stats['total']}")
    print(f"  Would improve: {score_stats['would_improve']}, Would degrade: {score_stats['would_degrade']}")
    if "embedding_mean" in score_stats:
        print(f"  Embedding mean: {score_stats['embedding_mean']}")
    if "composite_mean" in score_stats:
        print(f"  Composite mean: {score_stats['composite_mean']}, range: [{score_stats['composite_min']}, {score_stats['composite_max']}]")

    # B/C: Extraction stats
    print("\n[B/C] Extraction and confidence stats...")
    ext_stats = extraction_stats(db)
    with open(os.path.join(OUTDIR, "extraction_stats.json"), "w") as f:
        json.dump(ext_stats, f, indent=2)
    print(f"  Segments: {ext_stats['extracted']}/{ext_stats['total_segments']} ({ext_stats['coverage_pct']}%)")
    print(f"  Entities: {ext_stats['entities']}, Relations: {ext_stats['relations']}")
    if "entity_confidence" in ext_stats:
        print(f"  Entity confidence: mean={ext_stats['entity_confidence']['mean']}")
    if "relation_confidence" in ext_stats:
        print(f"  Relation confidence: mean={ext_stats['relation_confidence']['mean']}")

    # D/E: Graph reasoning
    print("\n[D/E] Graph reasoning and cross-paper synthesis...")
    reason_stats, path_evidence, synth_evidence = graph_reasoning_stats(repo)
    with open(os.path.join(OUTDIR, "reasoning_stats.json"), "w") as f:
        json.dump(reason_stats, f, indent=2)
    print(f"  Graph: {reason_stats['graph_nodes']} nodes, {reason_stats['graph_edges']} edges")
    print(f"  Paths: {reason_stats['paths_found']} total, {reason_stats['cross_paper_paths']} cross-paper")
    print(f"  Synthesis links: {reason_stats['synthesis_links']}")
    print(f"  Path evidence items: {reason_stats['path_evidence_items']}")
    print(f"  Synthesis evidence items: {reason_stats['synthesis_evidence_items']}")

    # I: Retrieval comparison v3
    print("\n[I] 3-way retrieval comparison v3 (current / KG / upgraded hybrid)...")
    comparison = run_retrieval_comparison_v3(repo, db, path_evidence, synth_evidence)
    print(f"  Current: mean_rel={comparison['current'].get('mean_relevance', 'N/A')}, "
          f"unique={comparison['current'].get('unique_source_ids', 'N/A')}")
    print(f"  KG:      mean_rel={comparison['shadow'].get('mean_relevance', 'N/A')}, "
          f"unique={comparison['shadow'].get('unique_source_ids', 'N/A')}")
    if "hybrid" in comparison:
        print(f"  Hybrid:  mean_rel={comparison['hybrid'].get('mean_relevance', 'N/A')}, "
              f"unique={comparison['hybrid'].get('unique_source_ids', 'N/A')}, "
              f"types={comparison['hybrid'].get('source_type_counts', {})}")
    print(f"  Shadow verdict: {comparison['verdict']}")
    print(f"  Hybrid verdict: {comparison['hybrid_verdict']}")

    # K: Switch readiness
    print("\n[K] Switch-readiness decision...")
    decision = switch_readiness(comparison)
    with open(os.path.join(OUTDIR, "switch_readiness.json"), "w") as f:
        json.dump(decision, f, indent=2)
    with open(os.path.join(OUTDIR, "switch_readiness.md"), "w") as f:
        f.write("# Switch-Readiness Decision — Phase 10E\n\n")
        f.write(f"**Recommendation:** `{decision['recommendation']}`\n\n")
        f.write(f"**Reason:** {decision['reason']}\n\n")
        if "checks" in decision:
            f.write("## Threshold Checks\n\n")
            f.write("| Check | Required | Actual | Result |\n")
            f.write("|-------|----------|--------|--------|\n")
            for k, v in decision["checks"].items():
                f.write(f"| {k} | {v['required']} | {v['actual']} | {'PASS' if v['pass'] else 'FAIL'} |\n")
    print(f"  Recommendation: {decision['recommendation']}")

    # L: Write-back status
    print("\n[L] Write-back status...")
    try:
        wbc = db.execute("SELECT COUNT(*) FROM bt_kg_findings").fetchone()[0]
        print(f"  bt_kg_findings: {wbc} rows, shadow-only, healthy")
    except:
        wbc = 0
        print("  bt_kg_findings: table not found or empty")

    # Manifest
    manifest = {
        "phase": "10E",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "deliverables": {
            "segment_rescoring": "segment_rescoring.json",
            "extraction_stats": "extraction_stats.json",
            "reasoning_stats": "reasoning_stats.json",
            "retrieval_comparison": "retrieval_comparison/retrieval_comparison_v3.json",
            "switch_readiness": "switch_readiness.json",
        },
    }
    with open(os.path.join(OUTDIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print("\n" + "=" * 60)
    print("Phase 10E pipeline complete.")
    print(f"Artifacts: {OUTDIR}")
    print("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
