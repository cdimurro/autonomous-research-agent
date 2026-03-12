"""KG-aware shadow retrieval source.

Phase 10A: Implements EvidenceSource ABC using bt_paper_segments,
bt_kg_entities, and bt_kg_relations. Shadow-only — does not replace
production retrieval.

The KGEvidenceSource gathers evidence from the knowledge graph tables
and returns standard EvidenceItem objects for drop-in compatibility.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from .db import Repository
from .evidence_source import EvidenceSource
from .models import EvidenceItem, new_id

logger = logging.getLogger(__name__)


class KGEvidenceSource(EvidenceSource):
    """Shadow retrieval source backed by the KG tables.

    Gathers evidence from:
    1. bt_paper_segments (scored/extracted segments)
    2. bt_kg_entities + bt_kg_relations (graph context)
    3. Optionally, upstream findings for bridge support

    Returns standard EvidenceItem objects.
    """

    def __init__(
        self,
        repo: Repository,
        include_upstream_findings: bool = False,
        min_relevance: float = 0.2,
        max_graph_hops: int = 1,
    ):
        self.repo = repo
        self.include_upstream_findings = include_upstream_findings
        self.min_relevance = min_relevance
        self.max_graph_hops = max_graph_hops

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        """Gather evidence from KG tables."""
        items: list[EvidenceItem] = []

        # 1. Get high-relevance paper segments
        segment_items = self._gather_from_segments(domain, limit)
        items.extend(segment_items)

        # 2. Enrich with graph context (entity/relation descriptions)
        graph_items = self._gather_from_graph(domain, max(0, limit - len(items)))
        items.extend(graph_items)

        # 3. Optionally include upstream findings
        if self.include_upstream_findings and len(items) < limit:
            upstream_items = self._gather_upstream_findings(
                domain, max(0, limit - len(items)),
            )
            items.extend(upstream_items)

        # Sort by relevance and trim
        items.sort(key=lambda x: x.relevance_score, reverse=True)
        result = items[:limit]

        logger.info(
            "KGEvidenceSource: domain=%s segments=%d graph=%d upstream=%d total=%d",
            domain, len(segment_items), len(graph_items),
            len(items) - len(segment_items) - len(graph_items),
            len(result),
        )
        return result

    def _gather_from_segments(self, domain: str, limit: int) -> list[EvidenceItem]:
        """Convert paper segments into EvidenceItems."""
        segments = self.repo.list_paper_segments(
            domain=domain, limit=limit,
        )

        items: list[EvidenceItem] = []
        for seg in segments:
            relevance = seg.get("relevance_score", 0.0)
            if relevance < self.min_relevance:
                continue

            text = seg.get("compressed_text") or seg.get("raw_text", "")
            if not text or len(text.strip()) < 20:
                continue

            items.append(EvidenceItem(
                id=new_id(),
                source_type="kg_segment",
                source_id=seg.get("source_id", seg.get("paper_id", "")),
                title=text[:120].rstrip(". ") + "...",
                quote=text[:500],
                citation=f"KG segment (paper={seg.get('paper_id', '')[:16]})",
                relevance_score=relevance,
            ))

        return items

    def _gather_from_graph(self, domain: str, limit: int) -> list[EvidenceItem]:
        """Build evidence items from entity-relation subgraphs."""
        if limit <= 0:
            return []

        entities = self.repo.list_kg_entities(domain=domain, limit=limit * 3)
        if not entities:
            return []

        items: list[EvidenceItem] = []
        seen_pairs: set[str] = set()

        for entity in entities[:limit * 2]:
            relations = self.repo.get_kg_relations_for_entity(entity["id"])
            if not relations:
                continue

            for rel in relations[:3]:
                pair_key = f"{rel['source_entity_id']}:{rel['target_entity_id']}"
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Build a quote from the relation
                quote = (
                    f"{entity['name']} ({entity.get('entity_type', 'concept')}) "
                    f"{rel.get('relation_type', 'related_to')} — "
                    f"{rel.get('description', 'related concept')}. "
                    f"Entity: {entity.get('description', '')}"
                )

                items.append(EvidenceItem(
                    id=new_id(),
                    source_type="kg_graph",
                    source_id=f"kg:{entity['id']}:{rel['id']}",
                    title=f"{entity['name']} [{rel.get('relation_type', '')}]",
                    quote=quote[:500],
                    citation=f"KG graph (domain={domain})",
                    relevance_score=min(
                        entity.get("confidence", 0.5),
                        rel.get("confidence", 0.5),
                    ),
                ))

                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break

        return items

    def _gather_upstream_findings(self, domain: str, limit: int) -> list[EvidenceItem]:
        """Fallback: gather from upstream findings table."""
        if limit <= 0:
            return []

        try:
            rows = self.repo.db.execute(
                """SELECT f.finding_id, f.content, f.provenance_quote,
                          f.confidence, p.title, p.arxiv_id, p.doi
                   FROM findings f
                   JOIN papers p ON f.paper_id = p.paper_id
                   WHERE f.judge_verdict = 'accepted'
                     AND (p.subjects LIKE ? OR p.title LIKE ?)
                   ORDER BY f.confidence DESC
                   LIMIT ?""",
                (f"%{domain}%", f"%{domain}%", limit),
            ).fetchall()
        except Exception as e:
            logger.debug("Upstream findings query failed: %s", e)
            return []

        items: list[EvidenceItem] = []
        for row in rows:
            quote = row[2] or row[1] or ""
            if not quote or len(quote.strip()) < 10:
                continue

            arxiv_id = row[5] or ""
            doi = row[6] or ""
            source_id = f"arxiv:{arxiv_id}" if arxiv_id else (f"doi:{doi}" if doi else f"finding:{row[0]}")

            items.append(EvidenceItem(
                id=new_id(),
                source_type="finding",
                source_id=source_id,
                title=(row[4] or "Unknown")[:200],
                quote=quote[:500],
                citation=f"upstream finding ({source_id[:30]})",
                relevance_score=float(row[3] or 0.5),
            ))

        return items
