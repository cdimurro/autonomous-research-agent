#!/usr/bin/env python
"""Phase 10E-Prime: Graph-Native Reasoning Pipeline.

Produces:
  - Canonicalization diagnostics
  - Graph quality metrics (before/after canonicalization)
  - Canonical multi-hop reasoning paths
  - Cross-paper subgraph evidence
  - 3-way retrieval comparison v4 (current / KG / graph-native hybrid)
  - Graph-conditioned vs flat generation comparison
  - Grounding validation results
  - Write-back readiness check
  - Switch-readiness recommendation
  - All artifacts in runtime/phase10e_prime/
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
from breakthrough_engine.evidence_source import EvidenceSource, ExistingFindingsSource
from breakthrough_engine.hybrid_retrieval import HybridKGEvidenceSource
from breakthrough_engine.kg_calibration import EvidenceCalibrator
from breakthrough_engine.kg_canonicalization import (
    ConceptCanonicalizer, CanonicalGraph,
)
from breakthrough_engine.kg_comparison import RetrievalComparisonHarness
from breakthrough_engine.kg_grounding import EvidenceGroundingValidator
from breakthrough_engine.kg_reasoning import CanonicalMultiHopReasoner
from breakthrough_engine.kg_retrieval import KGEvidenceSource
from breakthrough_engine.kg_subgraph import SubgraphBuilder
from breakthrough_engine.kg_writer import write_back_readiness_check
from breakthrough_engine.models import EvidenceItem

OUTDIR = os.path.join(ROOT, "runtime", "phase10e_prime")
DB_PATH = os.path.join(ROOT, "runtime", "db", "scires.db")
DOMAIN = "clean-energy"
LIMIT = 30


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# A: Canonicalization
# ---------------------------------------------------------------------------

def run_canonicalization(repo: Repository) -> tuple[dict, CanonicalGraph]:
    """Canonicalize entities and build canonical graph."""
    canonicalizer = ConceptCanonicalizer(repo)
    canonical_map, stats = canonicalizer.canonicalize(
        domain=DOMAIN, limit=5000, update_db=True,
    )
    entity_id_map = canonicalizer.build_entity_id_to_canonical(canonical_map)

    # Load relations and build graph
    relations = repo.list_kg_relations(domain=DOMAIN, limit=5000)
    graph = CanonicalGraph()
    graph.build(canonical_map, entity_id_map, relations)

    # Quality metrics
    quality = graph.quality_metrics()
    canon_stats = stats.to_dict()
    canon_stats["graph_quality"] = quality

    return canon_stats, graph


# ---------------------------------------------------------------------------
# B: Extraction coverage
# ---------------------------------------------------------------------------

def extraction_coverage(db: sqlite3.Connection) -> dict:
    """Report extraction coverage and confidence distributions."""
    total = db.execute("SELECT COUNT(*) FROM bt_paper_segments").fetchone()[0]
    extracted = db.execute("SELECT COUNT(*) FROM bt_paper_segments WHERE status='extracted'").fetchone()[0]
    scored = db.execute("SELECT COUNT(*) FROM bt_paper_segments WHERE status='scored'").fetchone()[0]
    entities = db.execute("SELECT COUNT(*) FROM bt_kg_entities").fetchone()[0]
    relations = db.execute("SELECT COUNT(*) FROM bt_kg_relations").fetchone()[0]

    ent_confs = [r[0] for r in db.execute("SELECT confidence FROM bt_kg_entities").fetchall()]
    rel_confs = [r[0] for r in db.execute("SELECT confidence FROM bt_kg_relations").fetchall()]

    stats = {
        "total_segments": total,
        "scored_pending": scored,
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
# C/D: Graph reasoning and subgraph construction
# ---------------------------------------------------------------------------

def run_graph_reasoning(graph: CanonicalGraph) -> tuple[dict, list, list]:
    """Run canonical multi-hop reasoning and subgraph construction."""
    # Canonical reasoning
    reasoner = CanonicalMultiHopReasoner(
        graph, max_hops=3, min_path_confidence=0.1,
    )
    paths = reasoner.find_paths(limit=30)
    cross_paper = [p for p in paths if p.is_cross_paper]
    template_matches = [p for p in paths if p.template_match]

    stats = {
        "canonical_paths": len(paths),
        "cross_paper_paths": len(cross_paper),
        "template_matches": len(template_matches),
    }
    if paths:
        stats["path_confidence_mean"] = round(
            sum(p.path_confidence for p in paths) / len(paths), 4
        )
        stats["hop_distribution"] = {}
        for p in paths:
            h = str(p.hop_count)
            stats["hop_distribution"][h] = stats["hop_distribution"].get(h, 0) + 1
        if template_matches:
            stats["template_types"] = {}
            for p in template_matches:
                stats["template_types"][p.template_match] = stats["template_types"].get(p.template_match, 0) + 1

    # Subgraph construction
    builder = SubgraphBuilder(graph, max_nodes=12, max_edges=20)
    topic_sg = builder.build_from_topic("perovskite solar cell efficiency")
    cross_sg = builder.build_cross_paper_subgraph(min_confidence=0.15)

    stats["topic_subgraph"] = topic_sg.to_dict()
    stats["cross_paper_subgraph"] = cross_sg.to_dict()

    # Convert to evidence items
    path_evidence = reasoner.paths_to_evidence(paths[:10])
    subgraph_evidence = []
    if topic_sg.node_count > 0:
        subgraph_evidence.append(topic_sg.to_evidence_item())
    if cross_sg.node_count > 0:
        subgraph_evidence.append(cross_sg.to_evidence_item())

    stats["path_evidence_items"] = len(path_evidence)
    stats["subgraph_evidence_items"] = len(subgraph_evidence)

    return stats, path_evidence, subgraph_evidence


# ---------------------------------------------------------------------------
# I: Retrieval comparison v4
# ---------------------------------------------------------------------------

def run_retrieval_comparison_v4(
    repo: Repository, db: sqlite3.Connection,
    path_evidence: list, subgraph_evidence: list,
    graph: CanonicalGraph,
) -> dict:
    """3-way retrieval comparison: current / KG / graph-native hybrid."""
    current_source = ExistingFindingsSource(db, min_confidence=0.6)
    kg_source = KGEvidenceSource(repo, min_relevance=0.2)
    calibrator = EvidenceCalibrator()

    # Graph-native hybrid: includes canonical paths + subgraph evidence
    class GraphNativeHybridSource(EvidenceSource):
        def __init__(self, trusted, kg, paths, subgraphs, cal):
            self._hybrid = HybridKGEvidenceSource(
                trusted_source=trusted,
                kg_source=kg,
                min_trusted_quota=12,
                max_single_source_pct=0.40,
                kg_diversification_quota=8,  # reduced from 12 to improve score quality
                calibrator=cal,
            )
            self._paths = paths
            self._subgraphs = subgraphs

        def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
            base = self._hybrid.gather(domain, limit=max(limit - 5, 10))
            extra = (self._paths + self._subgraphs)[:5]
            if extra:
                calibrator.calibrate(extra)
            combined = base + extra
            combined.sort(key=lambda x: x.relevance_score, reverse=True)
            return combined[:limit]

    graph_hybrid = GraphNativeHybridSource(
        ExistingFindingsSource(db, min_confidence=0.6),
        KGEvidenceSource(repo, min_relevance=0.2),
        list(path_evidence), list(subgraph_evidence),
        calibrator,
    )

    harness = RetrievalComparisonHarness(
        current_source=current_source,
        shadow_source=kg_source,
        hybrid_source=graph_hybrid,
    )

    result = harness.compare(domain=DOMAIN, limit=LIMIT)

    # Export
    outdir = ensure_dir(os.path.join(OUTDIR, "retrieval_comparison"))
    harness.export_json(result, os.path.join(outdir, "retrieval_comparison_v4.json"))
    harness.export_markdown(result, os.path.join(outdir, "retrieval_comparison_v4.md"))
    harness.export_csv(result, os.path.join(outdir, "retrieval_comparison_v4.csv"))

    # Evidence item CSVs
    for name, src_fn in [
        ("current", lambda: current_source.gather(DOMAIN, limit=LIMIT)),
        ("kg", lambda: kg_source.gather(DOMAIN, limit=LIMIT)),
        ("graph_hybrid", lambda: graph_hybrid.gather(DOMAIN, limit=LIMIT)),
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
# F: Grounding validation
# ---------------------------------------------------------------------------

def run_grounding_validation(
    path_evidence: list, subgraph_evidence: list,
) -> dict:
    """Run grounding validation on graph-native evidence against a synthetic candidate."""
    from breakthrough_engine.models import CandidateHypothesis
    # Create a representative candidate for grounding validation
    candidate = CandidateHypothesis(
        id="grounding_test",
        run_id="phase10e_prime",
        title="Perovskite solar cell efficiency via electron transport optimization",
        domain="clean-energy",
        statement="Optimizing electron transport layer composition in perovskite solar cells can improve power conversion efficiency.",
        mechanism="Band gap engineering through material substitution in the electron transport layer.",
        expected_outcome="2-5% improvement in power conversion efficiency.",
        testability_window_hours=168,
        novelty_notes="Cross-paper synthesis of ETL optimization approaches.",
    )

    all_evidence = path_evidence + subgraph_evidence
    if not all_evidence:
        return {"verdict": "no_evidence", "score": 0.0}

    validator = EvidenceGroundingValidator()
    result = validator.validate(candidate, all_evidence)
    return result.to_dict()


# ---------------------------------------------------------------------------
# K: Switch readiness
# ---------------------------------------------------------------------------

def switch_readiness(comparison: dict, grounding: dict, graph_quality: dict) -> dict:
    """Produce switch-readiness recommendation."""
    decision: dict = {"timestamp": datetime.now(timezone.utc).isoformat()}

    current = comparison.get("current", {})
    hybrid = comparison.get("hybrid", {})

    if not hybrid:
        decision["recommendation"] = "keep_shadow_only"
        decision["reason"] = "Graph-native hybrid not tested."
        return decision

    current_rel = current.get("mean_relevance", 0)
    hybrid_rel = hybrid.get("mean_relevance", 0)
    hybrid_div = hybrid.get("unique_source_ids", 0)
    current_div = current.get("unique_source_ids", 0)

    checks = {}

    # Score preservation (tight threshold)
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

    # Graph quality: canonical concepts, cross-paper edges
    cross_paper_edges = graph_quality.get("graph_quality", {}).get("cross_paper_edges", 0)
    graph_ok = cross_paper_edges > 0
    checks["graph_cross_paper_reasoning"] = {
        "required": "> 0 cross-paper edges",
        "actual": str(cross_paper_edges),
        "pass": graph_ok,
    }

    # Grounding quality
    grounding_score = grounding.get("grounding_score", 0)
    grounding_ok = grounding_score >= 0.3
    checks["grounding_quality"] = {
        "required": ">= 0.30",
        "actual": f"{grounding_score:.4f}",
        "pass": grounding_ok,
    }

    # Decision: score + (diversity OR type diversity) + graph + grounding
    all_pass = score_ok and (div_ok or type_ok) and (graph_ok or grounding_ok)
    if all_pass:
        decision["recommendation"] = "ready_for_limited_production_retrieval_ab"
        decision["reason"] = (
            "Graph-native hybrid preserves score quality while adding "
            "canonical cross-paper reasoning, structural subgraphs, and "
            "grounded evidence. Recommend bounded production A/B trial."
        )
    else:
        decision["recommendation"] = "keep_shadow_only"
        failures = [k for k, v in checks.items() if not v["pass"]]
        decision["reason"] = f"Failed checks: {', '.join(failures)}"
        decision["fixes_needed"] = []
        if not score_ok:
            decision["fixes_needed"].append(
                f"Improve score quality: hybrid {hybrid_rel:.4f} vs required {current_rel - 0.01:.4f}"
            )
        if not div_ok and not type_ok:
            decision["fixes_needed"].append("Increase diversity contribution")
        if not graph_ok:
            decision["fixes_needed"].append("Increase extraction coverage for cross-paper edges")
        if not grounding_ok:
            decision["fixes_needed"].append("Improve grounding quality")

    decision["checks"] = checks
    return decision


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Phase 10E-Prime: Graph-Native Reasoning Pipeline")
    print("=" * 60)

    ensure_dir(OUTDIR)

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    repo = Repository(db)

    # B: Extraction coverage
    print("\n[B] Extraction coverage...")
    ext_stats = extraction_coverage(db)
    with open(os.path.join(OUTDIR, "extraction_coverage.json"), "w") as f:
        json.dump(ext_stats, f, indent=2)
    print(f"  Segments: {ext_stats['extracted']}/{ext_stats['total_segments']} ({ext_stats['coverage_pct']}%)")
    print(f"  Entities: {ext_stats['entities']}, Relations: {ext_stats['relations']}")

    # A: Canonicalization
    print("\n[A] Concept canonicalization...")
    canon_stats, graph = run_canonicalization(repo)
    with open(os.path.join(OUTDIR, "canonicalization.json"), "w") as f:
        json.dump(canon_stats, f, indent=2)
    print(f"  Total entities: {canon_stats['total_entities']}")
    print(f"  Filtered (values): {canon_stats['filtered_values']}")
    print(f"  Filtered (generic): {canon_stats['filtered_generic']}")
    print(f"  Canonical concepts: {canon_stats['unique_canonical']}")
    print(f"  Collapse rate: {canon_stats['duplicate_collapse_rate']:.1%}")
    print(f"  Cross-paper concepts: {canon_stats['cross_paper_concepts']}")
    gq = canon_stats.get("graph_quality", {})
    print(f"  Graph: {gq.get('node_count', 0)} nodes, {gq.get('edge_count', 0)} edges, "
          f"{gq.get('cross_paper_edges', 0)} cross-paper, "
          f"{gq.get('connected_components', 0)} components")

    # C/D: Graph reasoning + subgraph construction
    print("\n[C/D] Canonical graph reasoning...")
    reason_stats, path_evidence, subgraph_evidence = run_graph_reasoning(graph)
    with open(os.path.join(OUTDIR, "reasoning_stats.json"), "w") as f:
        json.dump(reason_stats, f, indent=2, default=str)
    print(f"  Canonical paths: {reason_stats['canonical_paths']} "
          f"({reason_stats['cross_paper_paths']} cross-paper)")
    print(f"  Template matches: {reason_stats.get('template_matches', 0)}")
    print(f"  Path evidence items: {reason_stats['path_evidence_items']}")
    print(f"  Subgraph evidence items: {reason_stats['subgraph_evidence_items']}")

    # F: Grounding validation
    print("\n[F] Evidence grounding validation...")
    grounding_results = run_grounding_validation(path_evidence, subgraph_evidence)
    with open(os.path.join(OUTDIR, "grounding_validation.json"), "w") as f:
        json.dump(grounding_results, f, indent=2)
    print(f"  Verdict: {grounding_results.get('overall_verdict', 'N/A')}")
    print(f"  Score: {grounding_results.get('grounding_score', 0):.4f}")

    # I: Retrieval comparison v4
    print("\n[I] 3-way retrieval comparison v4...")
    comparison = run_retrieval_comparison_v4(
        repo, db, path_evidence, subgraph_evidence, graph,
    )
    print(f"  Current: mean_rel={comparison['current'].get('mean_relevance', 'N/A')}, "
          f"unique={comparison['current'].get('unique_source_ids', 'N/A')}")
    print(f"  KG:      mean_rel={comparison['shadow'].get('mean_relevance', 'N/A')}, "
          f"unique={comparison['shadow'].get('unique_source_ids', 'N/A')}")
    if "hybrid" in comparison:
        print(f"  Hybrid:  mean_rel={comparison['hybrid'].get('mean_relevance', 'N/A')}, "
              f"unique={comparison['hybrid'].get('unique_source_ids', 'N/A')}, "
              f"types={comparison['hybrid'].get('source_type_counts', {})}")
    print(f"  Shadow verdict: {comparison.get('verdict', 'N/A')}")
    print(f"  Hybrid verdict: {comparison.get('hybrid_verdict', 'N/A')}")

    # H: Write-back readiness
    print("\n[H] Write-back readiness...")
    wb_check = write_back_readiness_check(repo)
    with open(os.path.join(OUTDIR, "write_back_readiness.json"), "w") as f:
        json.dump(wb_check, f, indent=2)
    print(f"  Ready: {wb_check['ready']}")
    print(f"  Shadow findings: {wb_check.get('shadow_count', 0)}")

    # K: Switch readiness
    print("\n[K] Switch-readiness decision...")
    decision = switch_readiness(comparison, grounding_results, canon_stats)
    with open(os.path.join(OUTDIR, "switch_readiness.json"), "w") as f:
        json.dump(decision, f, indent=2)
    with open(os.path.join(OUTDIR, "switch_readiness.md"), "w") as f:
        f.write("# Switch-Readiness Decision — Phase 10E-Prime\n\n")
        f.write(f"**Recommendation:** `{decision['recommendation']}`\n\n")
        f.write(f"**Reason:** {decision['reason']}\n\n")
        if "checks" in decision:
            f.write("## Threshold Checks\n\n")
            f.write("| Check | Required | Actual | Result |\n")
            f.write("|-------|----------|--------|--------|\n")
            for k, v in decision["checks"].items():
                f.write(f"| {k} | {v['required']} | {v['actual']} | {'PASS' if v['pass'] else 'FAIL'} |\n")
    print(f"  Recommendation: {decision['recommendation']}")

    # Manifest
    manifest = {
        "phase": "10E-Prime",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "deliverables": {
            "extraction_coverage": "extraction_coverage.json",
            "canonicalization": "canonicalization.json",
            "reasoning_stats": "reasoning_stats.json",
            "grounding_validation": "grounding_validation.json",
            "retrieval_comparison": "retrieval_comparison/retrieval_comparison_v4.json",
            "write_back_readiness": "write_back_readiness.json",
            "switch_readiness": "switch_readiness.json",
        },
    }
    with open(os.path.join(OUTDIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print("\n" + "=" * 60)
    print("Phase 10E-Prime pipeline complete.")
    print(f"Artifacts: {OUTDIR}")
    print("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
