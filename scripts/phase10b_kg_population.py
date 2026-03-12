#!/usr/bin/env python3
"""Phase 10B: KG Population, Shadow Comparison, and Switch-Readiness.

Populates the KG with real clean-energy data, runs entity/relation extraction,
compares KG shadow retrieval against current production retrieval, and produces
a switch-readiness recommendation.

Usage:
    source .env
    PYTHONPATH=. .venv/bin/python scripts/phase10b_kg_population.py
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.embeddings import OllamaEmbeddingProvider
from breakthrough_engine.models import EvidenceItem, new_id
from breakthrough_engine.paper_ingestion import (
    PaperIngestionWorker,
    IngestionConfig,
    SegmentRelevanceScorer,
)
from breakthrough_engine.kg_extractor import (
    EntityRelationExtractor,
    ExtractionConfig,
)
from breakthrough_engine.kg_retrieval import KGEvidenceSource
from breakthrough_engine.kg_comparison import (
    RetrievalComparisonHarness,
    _compute_metrics,
    _compute_overlap,
    _verdict,
    ComparisonResult,
    SourceMetrics,
)
from breakthrough_engine.evidence_source import EvidenceSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("phase10b")

ARTIFACT_DIR = "runtime/phase10b"
DOMAIN = "clean-energy"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Current production evidence source (from bt_evidence_items)
# ---------------------------------------------------------------------------

class StoredEvidenceSource(EvidenceSource):
    """Retrieves evidence from bt_evidence_items — mirrors what production
    campaigns actually used."""

    def __init__(self, db: sqlite3.Connection):
        self._db = db

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        try:
            rows = self._db.execute(
                """SELECT id, source_id, source_type, title, quote,
                          citation, relevance_score
                   FROM bt_evidence_items
                   ORDER BY relevance_score DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        except Exception as e:
            logger.warning("StoredEvidenceSource query failed: %s", e)
            return []

        items = []
        for r in rows:
            items.append(EvidenceItem(
                id=r[0] or new_id(),
                source_id=r[1] or "",
                source_type=r[2] or "paper",
                title=(r[3] or "")[:200],
                quote=(r[4] or "")[:500],
                citation=r[5] or "",
                relevance_score=float(r[6] or 0.5),
            ))
        return items


# ---------------------------------------------------------------------------
# DELIVERABLE A: KG Population
# ---------------------------------------------------------------------------

def populate_kg(repo: Repository) -> dict:
    """Ingest from findings + evidence items with real embeddings."""
    logger.info("=== DELIVERABLE A: KG POPULATION ===")

    model = os.environ.get("BT_EMBEDDING_MODEL", "qwen3-embedding:4b")
    provider = OllamaEmbeddingProvider(model=model)
    dim = provider.dimension()
    logger.info("Embedding provider: %s (dim=%d)", type(provider).__name__, dim)

    # Skip if already populated
    existing = repo.count_paper_segments(domain=DOMAIN)
    if existing > 0:
        logger.info("KG already has %d segments — skipping ingestion", existing)
        scored = repo.count_paper_segments(domain=DOMAIN, status="scored")
        ingested = repo.count_paper_segments(domain=DOMAIN, status="ingested")
        summary = {
            "timestamp": _utcnow(),
            "domain": DOMAIN,
            "findings_ingested": 0,
            "findings_errors": 0,
            "evidence_items_ingested": 0,
            "evidence_items_errors": 0,
            "total_segments": existing,
            "scored_segments": scored,
            "ingested_segments": ingested,
            "embedding_provider": type(provider).__name__,
            "embedding_dimension": dim,
            "note": "skipped — already populated",
        }
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        with open(f"{ARTIFACT_DIR}/kg_population_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        return summary

    config = IngestionConfig(
        domain=DOMAIN,
        limit=200,  # ingest all available
        compress=False,  # skip compression for speed
    )
    worker = PaperIngestionWorker(repo, embedding_provider=provider, config=config)

    # Ingest from findings table
    logger.info("Ingesting from findings table...")
    findings_stats = worker.ingest_from_findings(domain=DOMAIN, limit=200)
    logger.info("Findings ingestion: %s", findings_stats)

    # Ingest from evidence items
    logger.info("Ingesting from bt_evidence_items...")
    evidence_stats = worker.ingest_from_evidence_items(domain=DOMAIN, limit=500)
    logger.info("Evidence items ingestion: %s", evidence_stats)

    # Counts
    total_segments = repo.count_paper_segments(domain=DOMAIN)
    scored = repo.count_paper_segments(domain=DOMAIN, status="scored")
    ingested = repo.count_paper_segments(domain=DOMAIN, status="ingested")

    summary = {
        "timestamp": _utcnow(),
        "domain": DOMAIN,
        "findings_ingested": findings_stats.get("ingested", 0),
        "findings_errors": findings_stats.get("errors", 0),
        "evidence_items_ingested": evidence_stats.get("ingested", 0),
        "evidence_items_errors": evidence_stats.get("errors", 0),
        "total_segments": total_segments,
        "scored_segments": scored,
        "ingested_segments": ingested,
        "embedding_provider": type(provider).__name__,
        "embedding_dimension": dim,
    }

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    with open(f"{ARTIFACT_DIR}/kg_population_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("Population complete: %d total segments (%d scored)", total_segments, scored)
    return summary


# ---------------------------------------------------------------------------
# DELIVERABLE A (continued): Entity/Relation Extraction
# ---------------------------------------------------------------------------

def run_extraction(repo: Repository) -> dict:
    """Run real LLM extraction on scored segments."""
    logger.info("=== ENTITY/RELATION EXTRACTION ===")

    # Skip if extraction is already running or has produced results
    existing_entities = len(repo.list_kg_entities(domain=DOMAIN, limit=1))
    if existing_entities > 0:
        entities = repo.list_kg_entities(domain=DOMAIN, limit=1000)
        relations = repo.list_kg_relations(domain=DOMAIN, limit=1000)
        extracted = repo.count_paper_segments(domain=DOMAIN, status="extracted")
        stats = {
            "segments_processed": extracted,
            "entities_extracted": len(entities),
            "relations_extracted": len(relations),
            "errors": 0,
            "domain": DOMAIN,
            "note": "skipped — extraction already has results (may still be running in background)",
        }
        logger.info("Extraction already has %d entities — skipping", len(entities))
        with open(f"{ARTIFACT_DIR}/extraction_stats.json", "w") as f:
            json.dump(stats, f, indent=2)
        return stats

    config = ExtractionConfig()
    extractor = EntityRelationExtractor(repo, config=config, mock=False)

    stats = extractor.extract_from_segments(domain=DOMAIN, limit=200)
    logger.info("Extraction stats: %s", stats)

    # Save
    with open(f"{ARTIFACT_DIR}/extraction_stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    return stats


# ---------------------------------------------------------------------------
# DELIVERABLE B: Quality Audit
# ---------------------------------------------------------------------------

def audit_quality(repo: Repository) -> dict:
    """Audit KG extraction quality."""
    logger.info("=== DELIVERABLE B: KG QUALITY AUDIT ===")

    entities = repo.list_kg_entities(domain=DOMAIN, limit=1000)
    relations = repo.list_kg_relations(domain=DOMAIN, limit=1000)

    # Entity analysis
    type_counts = Counter(e.get("entity_type", "unknown") for e in entities)
    confidence_vals = [e.get("confidence", 0) for e in entities]
    names = [e.get("name", "") for e in entities]
    canonical_names = [e.get("canonical_name", "") for e in entities]
    name_counts = Counter(canonical_names)
    duplicates = {n: c for n, c in name_counts.items() if c > 1}

    # Relation analysis
    rel_type_counts = Counter(r.get("relation_type", "unknown") for r in relations)

    # Empty/garbage detection
    empty_entities = sum(1 for e in entities if not e.get("name", "").strip())
    short_entities = sum(1 for e in entities if len(e.get("name", "").strip()) < 3)
    empty_descriptions = sum(1 for e in entities if not e.get("description", "").strip())

    audit = {
        "timestamp": _utcnow(),
        "entity_count": len(entities),
        "relation_count": len(relations),
        "entity_type_distribution": dict(type_counts.most_common()),
        "relation_type_distribution": dict(rel_type_counts.most_common()),
        "confidence_stats": {
            "mean": round(sum(confidence_vals) / len(confidence_vals), 4) if confidence_vals else 0,
            "min": round(min(confidence_vals), 4) if confidence_vals else 0,
            "max": round(max(confidence_vals), 4) if confidence_vals else 0,
        },
        "duplicate_entities": len(duplicates),
        "duplicate_details": {k: v for k, v in sorted(duplicates.items(), key=lambda x: -x[1])[:20]},
        "empty_entity_names": empty_entities,
        "short_entity_names": short_entities,
        "empty_descriptions": empty_descriptions,
        "sample_entities": [
            {"name": e["name"], "type": e.get("entity_type"), "desc": e.get("description", "")[:80]}
            for e in entities[:15]
        ],
        "sample_relations": [
            {"type": r.get("relation_type"), "desc": r.get("description", "")[:80]}
            for r in relations[:10]
        ],
    }

    with open(f"{ARTIFACT_DIR}/quality_audit.json", "w") as f:
        json.dump(audit, f, indent=2)

    # Markdown report
    lines = [
        "# KG Quality Audit — Phase 10B",
        f"",
        f"**Timestamp:** {audit['timestamp']}",
        f"**Entities:** {len(entities)}",
        f"**Relations:** {len(relations)}",
        f"",
        "## Entity Type Distribution",
    ]
    for t, c in type_counts.most_common():
        lines.append(f"- {t}: {c}")
    lines += [
        "",
        "## Relation Type Distribution",
    ]
    for t, c in rel_type_counts.most_common():
        lines.append(f"- {t}: {c}")
    lines += [
        "",
        f"## Quality Flags",
        f"- Duplicate canonical names: {len(duplicates)}",
        f"- Empty entity names: {empty_entities}",
        f"- Short entity names (<3 chars): {short_entities}",
        f"- Empty descriptions: {empty_descriptions}",
        f"- Mean confidence: {audit['confidence_stats']['mean']}",
    ]
    if duplicates:
        lines += ["", "## Top Duplicates"]
        for name, count in sorted(duplicates.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"- `{name}`: {count} occurrences")

    with open(f"{ARTIFACT_DIR}/quality_audit.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    logger.info("Quality audit: %d entities, %d relations, %d duplicates",
                len(entities), len(relations), len(duplicates))
    return audit


# ---------------------------------------------------------------------------
# DELIVERABLE C: Retrieval-Level Shadow Comparison
# ---------------------------------------------------------------------------

def run_retrieval_comparison(repo: Repository) -> dict:
    """Compare current production retrieval vs KG shadow retrieval."""
    logger.info("=== DELIVERABLE C: RETRIEVAL-LEVEL COMPARISON ===")

    db = repo.db

    # Current production evidence source
    current_source = StoredEvidenceSource(db)

    # KG shadow source
    shadow_source = KGEvidenceSource(
        repo,
        include_upstream_findings=True,  # include upstream for fuller picture
        min_relevance=0.15,
    )

    harness = RetrievalComparisonHarness(current_source, shadow_source)
    result = harness.compare(domain=DOMAIN, limit=30)

    # Export standard artifacts
    comp_dir = f"{ARTIFACT_DIR}/retrieval_comparison"
    os.makedirs(comp_dir, exist_ok=True)
    harness.export_json(result, f"{comp_dir}/retrieval_comparison.json")
    harness.export_markdown(result, f"{comp_dir}/retrieval_comparison.md")
    harness.export_csv(result, f"{comp_dir}/retrieval_comparison.csv")

    # Export evidence items CSVs
    current_items = current_source.gather(DOMAIN, limit=30)
    shadow_items = shadow_source.gather(DOMAIN, limit=30)

    for items, label in [(current_items, "current"), (shadow_items, "kg")]:
        with open(f"{comp_dir}/evidence_items_{label}.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "source_type", "source_id", "title", "relevance_score", "quote_len"])
            for it in items:
                writer.writerow([
                    it.id[:16], it.source_type, it.source_id[:40],
                    it.title[:80], round(it.relevance_score, 4), len(it.quote),
                ])

    # Compute diversity metrics
    current_types = Counter(it.source_type for it in current_items)
    shadow_types = Counter(it.source_type for it in shadow_items)
    current_sources = set(it.source_id for it in current_items)
    shadow_sources = set(it.source_id for it in shadow_items)

    # Dominance concentration (what fraction comes from top source)
    current_source_counts = Counter(it.source_id for it in current_items)
    shadow_source_counts = Counter(it.source_id for it in shadow_items)
    current_top_frac = (current_source_counts.most_common(1)[0][1] / len(current_items)
                        if current_items else 0)
    shadow_top_frac = (shadow_source_counts.most_common(1)[0][1] / len(shadow_items)
                       if shadow_items else 0)

    diversity_summary = {
        "current": {
            "item_count": len(current_items),
            "unique_sources": len(current_sources),
            "source_types": dict(current_types),
            "top_source_concentration": round(current_top_frac, 3),
        },
        "shadow": {
            "item_count": len(shadow_items),
            "unique_sources": len(shadow_sources),
            "source_types": dict(shadow_types),
            "top_source_concentration": round(shadow_top_frac, 3),
        },
        "verdict": result.verdict,
        "notes": result.notes,
    }

    with open(f"{comp_dir}/diversity_summary.json", "w") as f:
        json.dump(diversity_summary, f, indent=2)

    logger.info("Retrieval comparison verdict: %s", result.verdict)
    logger.info("Current: %d items, %d unique sources, top concentration %.1f%%",
                len(current_items), len(current_sources), current_top_frac * 100)
    logger.info("Shadow: %d items, %d unique sources, top concentration %.1f%%",
                len(shadow_items), len(shadow_sources), shadow_top_frac * 100)

    return diversity_summary


# ---------------------------------------------------------------------------
# DELIVERABLE D: Campaign-Level Shadow Comparison (bounded)
# ---------------------------------------------------------------------------

def run_campaign_comparison(repo: Repository) -> dict:
    """Run bounded campaign-level comparison.

    Since running actual campaigns requires the full Ollama generation pipeline
    and would take significant time, we do a simulated comparison using the
    evidence packs from recent production campaigns and comparing what the KG
    retrieval would have provided for the same domains.
    """
    logger.info("=== DELIVERABLE D: CAMPAIGN-LEVEL COMPARISON ===")

    db = repo.db
    camp_dir = f"{ARTIFACT_DIR}/campaign_comparison"
    os.makedirs(camp_dir, exist_ok=True)

    # Get recent production campaigns and their evidence packs
    try:
        campaigns = db.execute(
            """SELECT DISTINCT dc.id, dc.domain, dc.profile_name, dc.status,
                      r.run_id, r.status as run_status
               FROM bt_daily_campaigns dc
               JOIN bt_runs r ON r.run_id LIKE '%' || substr(dc.id, 1, 8) || '%'
               WHERE dc.status IN ('completed', 'approved')
               ORDER BY dc.started_at DESC
               LIMIT 6""",
        ).fetchall()
    except Exception:
        campaigns = []

    if not campaigns:
        # Fallback: use runs directly
        try:
            campaigns = db.execute(
                """SELECT run_id, 'clean-energy' as domain, 'production' as profile,
                          status, run_id, status
                   FROM bt_runs
                   WHERE status = 'COMPLETED'
                   ORDER BY started_at DESC
                   LIMIT 6""",
            ).fetchall()
        except Exception:
            campaigns = []

    # Get candidates and their scores from recent runs
    try:
        recent_candidates = db.execute(
            """SELECT c.id, c.title, c.domain,
                      s.plausibility_score, s.novelty_score, s.evidence_strength_score,
                      s.final_score, c.run_id,
                      c.status
               FROM bt_candidates c
               LEFT JOIN bt_scores s ON c.id = s.candidate_id
               WHERE c.domain LIKE '%clean%' OR c.domain LIKE '%energy%'
               ORDER BY s.final_score DESC
               LIMIT 50""",
        ).fetchall()
    except Exception as e:
        logger.warning("Cannot query candidates: %s", e)
        recent_candidates = []

    # Get evidence items used in recent runs
    try:
        evidence_packs = db.execute(
            """SELECT ep.id, ep.candidate_id, ei.source_type, ei.source_id,
                      ei.title, ei.relevance_score
               FROM bt_evidence_packs ep
               JOIN bt_evidence_items ei ON ep.id = ei.pack_id
               ORDER BY ep.created_at DESC
               LIMIT 200""",
        ).fetchall()
    except Exception as e:
        logger.warning("Cannot query evidence packs: %s", e)
        evidence_packs = []

    # Compute current evidence diversity across recent campaigns
    current_evidence_sources = Counter()
    current_evidence_types = Counter()
    for ep in evidence_packs:
        current_evidence_sources[ep[3]] += 1  # source_id
        current_evidence_types[ep[2]] += 1  # source_type

    # Now get what KG would provide
    shadow_source = KGEvidenceSource(repo, include_upstream_findings=True, min_relevance=0.15)
    kg_items = shadow_source.gather(DOMAIN, limit=50)
    kg_sources = Counter(it.source_id for it in kg_items)
    kg_types = Counter(it.source_type for it in kg_items)

    # Candidate quality from recent production
    candidate_scores = []
    for c in recent_candidates:
        if c[6]:  # overall_score
            candidate_scores.append({
                "title": c[1][:80],
                "plausibility": c[3],
                "novelty": c[4],
                "falsifiability": c[5],
                "overall": c[6],
                "status": c[8],
            })

    # Campaign-level summary
    campaign_summary = {
        "timestamp": _utcnow(),
        "domain": DOMAIN,
        "production_campaigns_analyzed": len(campaigns),
        "production_candidates_scored": len(candidate_scores),
        "production_evidence_items": len(evidence_packs),
        "production_evidence_diversity": {
            "unique_sources": len(current_evidence_sources),
            "source_types": dict(current_evidence_types),
            "top_source_count": current_evidence_sources.most_common(1)[0][1] if current_evidence_sources else 0,
            "top_3_sources": [
                {"source": s, "count": c}
                for s, c in current_evidence_sources.most_common(3)
            ],
        },
        "kg_shadow_evidence": {
            "items_available": len(kg_items),
            "unique_sources": len(kg_sources),
            "source_types": dict(kg_types),
            "top_source_concentration": (
                kg_sources.most_common(1)[0][1] / len(kg_items)
                if kg_items else 0
            ),
        },
        "candidate_quality_stats": {
            "count": len(candidate_scores),
            "mean_overall": round(
                sum(c["overall"] for c in candidate_scores) / len(candidate_scores), 4
            ) if candidate_scores else 0,
            "mean_plausibility": round(
                sum(c["plausibility"] for c in candidate_scores if c["plausibility"]) / max(1, sum(1 for c in candidate_scores if c["plausibility"])), 4
            ) if candidate_scores else 0,
            "mean_novelty": round(
                sum(c["novelty"] for c in candidate_scores if c["novelty"]) / max(1, sum(1 for c in candidate_scores if c["novelty"])), 4
            ) if candidate_scores else 0,
        },
        "diversity_improvement_potential": {
            "current_unique_sources": len(current_evidence_sources),
            "kg_unique_sources": len(kg_sources),
            "improvement_ratio": round(
                len(kg_sources) / max(1, len(current_evidence_sources)), 2
            ),
            "current_concentration_top1": round(
                (current_evidence_sources.most_common(1)[0][1] / len(evidence_packs))
                if evidence_packs else 0, 3
            ),
            "kg_concentration_top1": round(
                (kg_sources.most_common(1)[0][1] / len(kg_items))
                if kg_items else 0, 3
            ),
        },
    }

    with open(f"{camp_dir}/campaign_comparison.json", "w") as f:
        json.dump(campaign_summary, f, indent=2)

    # Export candidates CSV
    with open(f"{camp_dir}/recent_candidates.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "plausibility", "novelty", "falsifiability", "overall", "status"])
        for c in candidate_scores[:30]:
            writer.writerow([
                c["title"], c.get("plausibility"), c.get("novelty"),
                c.get("falsifiability"), c["overall"], c["status"],
            ])

    # Markdown
    lines = [
        "# Campaign-Level Shadow Comparison — Phase 10B",
        f"",
        f"**Timestamp:** {campaign_summary['timestamp']}",
        f"**Domain:** {DOMAIN}",
        f"",
        "## Production Campaign Evidence",
        f"- Evidence items analyzed: {len(evidence_packs)}",
        f"- Unique sources: {len(current_evidence_sources)}",
        f"- Source types: {dict(current_evidence_types)}",
        f"",
        "## KG Shadow Evidence",
        f"- Items available: {len(kg_items)}",
        f"- Unique sources: {len(kg_sources)}",
        f"- Source types: {dict(kg_types)}",
        f"",
        "## Diversity Improvement Potential",
        f"- Current unique sources: {len(current_evidence_sources)}",
        f"- KG unique sources: {len(kg_sources)}",
        f"- Improvement ratio: {campaign_summary['diversity_improvement_potential']['improvement_ratio']}x",
        f"- Current top-1 concentration: {campaign_summary['diversity_improvement_potential']['current_concentration_top1']:.1%}",
        f"- KG top-1 concentration: {campaign_summary['diversity_improvement_potential']['kg_concentration_top1']:.1%}",
        f"",
        "## Candidate Quality (Recent Production)",
        f"- Candidates scored: {len(candidate_scores)}",
        f"- Mean overall score: {campaign_summary['candidate_quality_stats']['mean_overall']}",
    ]

    with open(f"{camp_dir}/campaign_comparison.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    logger.info("Campaign comparison: %d evidence packs, %d candidates, "
                "diversity ratio %.2fx",
                len(evidence_packs), len(candidate_scores),
                campaign_summary['diversity_improvement_potential']['improvement_ratio'])

    return campaign_summary


# ---------------------------------------------------------------------------
# DELIVERABLE E: Switch-Readiness
# ---------------------------------------------------------------------------

def assess_switch_readiness(
    population: dict, audit: dict, retrieval: dict, campaign: dict,
) -> dict:
    """Produce switch-readiness recommendation."""
    logger.info("=== DELIVERABLE E: SWITCH-READINESS ASSESSMENT ===")

    issues = []
    strengths = []

    # Check population adequacy
    if population.get("total_segments", 0) < 10:
        issues.append("KG has fewer than 10 segments — insufficient data")
    else:
        strengths.append(f"KG has {population['total_segments']} segments")

    # Check extraction quality
    if audit.get("entity_count", 0) < 5:
        issues.append("Fewer than 5 entities extracted — extraction may have failed")
    else:
        strengths.append(f"{audit['entity_count']} entities, {audit['relation_count']} relations extracted")

    if audit.get("empty_entity_names", 0) > audit.get("entity_count", 1) * 0.1:
        issues.append("High rate of empty entity names")

    # Check retrieval comparison
    verdict = retrieval.get("verdict", "inconclusive")
    if verdict == "shadow_better":
        strengths.append("KG shadow retrieval outperforms current retrieval")
    elif verdict == "shadow_empty":
        issues.append("KG shadow retrieval returned no items")
    elif verdict == "current_better":
        issues.append("Current retrieval still outperforms KG shadow")

    # Check diversity improvement
    div = campaign.get("diversity_improvement_potential", {})
    ratio = div.get("improvement_ratio", 0)
    if ratio > 1.2:
        strengths.append(f"KG offers {ratio:.1f}x source diversity improvement")
    elif ratio < 0.8:
        issues.append("KG has worse source diversity than current")

    kg_concentration = div.get("kg_concentration_top1", 1.0)
    current_concentration = div.get("current_concentration_top1", 1.0)
    if kg_concentration < current_concentration:
        strengths.append(f"KG reduces top-1 concentration from {current_concentration:.1%} to {kg_concentration:.1%}")

    # Decision
    if len(issues) == 0 and verdict == "shadow_better":
        recommendation = "ready_for_retrieval_ab"
        reason = "KG retrieval outperforms current on diversity and quality metrics"
        next_experiment = {
            "campaign_count": "6+6 (6 current, 6 KG)",
            "profile": "evaluation_daily_clean_energy",
            "success_metrics": [
                "KG arm mean score >= current arm mean score - 0.02",
                "KG arm source diversity >= current arm",
                "KG arm approval rate >= 60%",
            ],
            "rollback_criteria": [
                "KG arm mean score < current - 0.05",
                "KG arm approval rate < 40%",
            ],
        }
    elif len(issues) <= 1 and verdict in ("shadow_better", "comparable"):
        recommendation = "ready_for_retrieval_ab"
        reason = f"KG retrieval is {'better' if verdict == 'shadow_better' else 'comparable'} with minor issues: {'; '.join(issues) if issues else 'none'}"
        next_experiment = {
            "campaign_count": "6+6",
            "profile": "evaluation_daily_clean_energy",
            "success_metrics": [
                "KG arm mean score >= current arm mean score - 0.02",
                "KG arm source diversity >= current arm",
            ],
            "rollback_criteria": [
                "KG arm mean score < current - 0.05",
                "KG arm approval rate < 40%",
            ],
        }
    elif len(issues) <= 2:
        recommendation = "shadow_only_continue"
        reason = f"KG shows promise but needs more data/refinement: {'; '.join(issues)}"
        next_experiment = None
    else:
        recommendation = "not_ready_fix_kg_first"
        reason = f"Multiple issues prevent A/B trial: {'; '.join(issues)}"
        next_experiment = None

    fixes_needed = issues[:3] if issues else []

    decision = {
        "timestamp": _utcnow(),
        "recommendation": recommendation,
        "reason": reason,
        "strengths": strengths,
        "issues": issues,
        "fixes_needed": fixes_needed,
        "next_experiment": next_experiment,
    }

    with open(f"{ARTIFACT_DIR}/switch_readiness.json", "w") as f:
        json.dump(decision, f, indent=2)

    # Markdown
    lines = [
        "# Switch-Readiness Decision — Phase 10B",
        f"",
        f"**Recommendation:** `{recommendation}`",
        f"**Reason:** {reason}",
        f"",
        "## Strengths",
    ]
    for s in strengths:
        lines.append(f"- {s}")
    lines += ["", "## Issues"]
    for i in issues:
        lines.append(f"- {i}")
    if next_experiment:
        lines += [
            "",
            "## Next Experiment",
            f"- Campaign count: {next_experiment['campaign_count']}",
            f"- Profile: {next_experiment['profile']}",
            "- Success metrics:",
        ]
        for m in next_experiment["success_metrics"]:
            lines.append(f"  - {m}")
        lines.append("- Rollback criteria:")
        for r in next_experiment["rollback_criteria"]:
            lines.append(f"  - {r}")
    if fixes_needed:
        lines += ["", "## Fixes Needed"]
        for fix in fixes_needed:
            lines.append(f"1. {fix}")

    with open(f"{ARTIFACT_DIR}/switch_readiness.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    logger.info("Switch-readiness: %s — %s", recommendation, reason)
    return decision


# ---------------------------------------------------------------------------
# DELIVERABLE F: Write-Back Status
# ---------------------------------------------------------------------------

def check_writeback(repo: Repository) -> dict:
    """Verify write-back scaffold health."""
    logger.info("=== DELIVERABLE F: WRITE-BACK STATUS CHECK ===")

    from breakthrough_engine.kg_writer import list_active_findings, list_shadow_findings

    active = list_active_findings(repo, domain=DOMAIN)
    shadow = list_shadow_findings(repo, domain=DOMAIN)

    # Check table exists and is functional
    try:
        repo.db.execute("SELECT COUNT(*) FROM bt_kg_findings").fetchone()
        table_healthy = True
    except Exception:
        table_healthy = False

    status = {
        "timestamp": _utcnow(),
        "table_healthy": table_healthy,
        "active_findings": len(active),
        "shadow_findings": len(shadow),
        "writeback_mode": "shadow_only",
        "policy_conflict_risk": "none — write-back is shadow-only and does not affect policy learning",
        "ready_for_future_activation": table_healthy,
    }

    with open(f"{ARTIFACT_DIR}/writeback_status.json", "w") as f:
        json.dump(status, f, indent=2)

    logger.info("Write-back: table_healthy=%s, active=%d, shadow=%d",
                table_healthy, len(active), len(shadow))
    return status


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    start = time.time()
    logger.info("Phase 10B: KG Population, Shadow Comparison, Switch-Readiness")
    logger.info("Domain: %s", DOMAIN)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    db = init_db("runtime/db/scires.db")
    repo = Repository(db)

    # A: Populate
    pop = populate_kg(repo)
    print(f"\n[A] Population: {pop['total_segments']} segments "
          f"({pop['scored_segments']} scored)")

    # A+: Extract
    ext = run_extraction(repo)
    print(f"[A+] Extraction: {ext['entities_extracted']} entities, "
          f"{ext['relations_extracted']} relations, {ext['errors']} errors")

    # B: Quality audit
    audit = audit_quality(repo)
    print(f"[B] Audit: {audit['entity_count']} entities, "
          f"{audit['relation_count']} relations, "
          f"{audit['duplicate_entities']} duplicates")

    # C: Retrieval comparison
    retrieval = run_retrieval_comparison(repo)
    print(f"[C] Retrieval: verdict={retrieval['verdict']}")
    print(f"    Current: {retrieval['current']['item_count']} items, "
          f"{retrieval['current']['unique_sources']} sources")
    print(f"    Shadow:  {retrieval['shadow']['item_count']} items, "
          f"{retrieval['shadow']['unique_sources']} sources")

    # D: Campaign comparison
    campaign = run_campaign_comparison(repo)
    print(f"[D] Campaign: diversity ratio "
          f"{campaign['diversity_improvement_potential']['improvement_ratio']}x")

    # E: Switch-readiness
    decision = assess_switch_readiness(pop, audit, retrieval, campaign)
    print(f"\n[E] RECOMMENDATION: {decision['recommendation']}")
    print(f"    Reason: {decision['reason']}")

    # F: Write-back
    wb = check_writeback(repo)
    print(f"[F] Write-back: healthy={wb['table_healthy']}, mode={wb['writeback_mode']}")

    # Final manifest
    manifest = {
        "phase": "10B",
        "timestamp": _utcnow(),
        "duration_seconds": round(time.time() - start, 1),
        "artifacts": [
            "kg_population_summary.json",
            "extraction_stats.json",
            "quality_audit.json",
            "quality_audit.md",
            "retrieval_comparison/retrieval_comparison.json",
            "retrieval_comparison/retrieval_comparison.md",
            "retrieval_comparison/retrieval_comparison.csv",
            "retrieval_comparison/evidence_items_current.csv",
            "retrieval_comparison/evidence_items_kg.csv",
            "retrieval_comparison/diversity_summary.json",
            "campaign_comparison/campaign_comparison.json",
            "campaign_comparison/campaign_comparison.md",
            "campaign_comparison/recent_candidates.csv",
            "switch_readiness.json",
            "switch_readiness.md",
            "writeback_status.json",
            "manifest.json",
        ],
        "recommendation": decision["recommendation"],
    }

    with open(f"{ARTIFACT_DIR}/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    elapsed = round(time.time() - start, 1)
    print(f"\nPhase 10B complete in {elapsed}s. Artifacts: {ARTIFACT_DIR}/")

    db.close()


if __name__ == "__main__":
    main()
