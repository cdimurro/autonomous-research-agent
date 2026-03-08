"""Evidence ingestion boundary - adapters for gathering evidence.

Keeps evidence retrieval cleanly separated from orchestration.
Adapters:
- DemoFixtureSource: hardcoded fixtures for tests/demos
- ExistingFindingsSource: reads from scires.db findings table with filtering
- FutureRetrievalSource: stub for future literature search APIs
"""

from __future__ import annotations

import abc
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from .models import EvidenceItem, new_id

logger = logging.getLogger(__name__)


class EvidenceSource(abc.ABC):
    """Abstract interface for evidence retrieval."""

    @abc.abstractmethod
    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        """Return a list of evidence items for the given domain."""


class DemoFixtureSource(EvidenceSource):
    """Returns hardcoded demo evidence for tests and demos."""

    FIXTURES: list[dict] = [
        {
            "source_type": "paper",
            "source_id": "arxiv:2401.00001",
            "title": "Novel Perovskite Solar Cell Efficiency Gains",
            "quote": "We observed a 23.7% power conversion efficiency using a methylammonium-free perovskite composition, exceeding the previous record of 22.1% for single-junction cells.",
            "citation": "Zhang et al., Nature Energy, 2024",
            "relevance_score": 0.85,
        },
        {
            "source_type": "paper",
            "source_id": "arxiv:2401.00002",
            "title": "Topological Insulator Thermoelectric Enhancement",
            "quote": "Bi2Te3 nanoribbons exhibited a thermoelectric figure of merit ZT=2.4 at 300K, a 40% improvement attributed to surface-state phonon scattering suppression.",
            "citation": "Kim et al., Science, 2024",
            "relevance_score": 0.82,
        },
        {
            "source_type": "paper",
            "source_id": "doi:10.1038/s41586-024-00003",
            "title": "CRISPR-Cas13 Rapid Pathogen Detection",
            "quote": "Our CRISPR-Cas13 lateral flow assay detected SARS-CoV-2 RNA at 10 copies/uL within 35 minutes, achieving 98.5% sensitivity and 99.1% specificity in clinical samples.",
            "citation": "Patel et al., Nature, 2024",
            "relevance_score": 0.90,
        },
        {
            "source_type": "paper",
            "source_id": "arxiv:2401.00004",
            "title": "Room-Temperature Superconductor Lattice Prediction",
            "quote": "DFT calculations predict that LaH10 at 170 GPa exhibits superconducting Tc of 250K, consistent with experimental measurements of 260K +/- 10K.",
            "citation": "Li et al., Physical Review Letters, 2024",
            "relevance_score": 0.78,
        },
        {
            "source_type": "paper",
            "source_id": "arxiv:2401.00005",
            "title": "Carbon Capture via Metal-Organic Frameworks",
            "quote": "MOF-303 demonstrated CO2 uptake of 8.2 mmol/g at 1 bar and 25C with >95% selectivity over N2, showing minimal capacity loss after 500 adsorption-desorption cycles.",
            "citation": "Rodriguez et al., JACS, 2024",
            "relevance_score": 0.88,
        },
        {
            "source_type": "paper",
            "source_id": "arxiv:2401.00006",
            "title": "Neuromorphic Chip Energy Efficiency",
            "quote": "The spiking neural network accelerator achieved 1.2 TOPS/W for inference tasks, a 10x improvement over conventional GPU architectures on equivalent workloads.",
            "citation": "Wang et al., IEEE ISSCC, 2024",
            "relevance_score": 0.80,
        },
    ]

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        results = []
        for fix in self.FIXTURES[:limit]:
            results.append(EvidenceItem(id=new_id(), **fix))
        return results


class ExistingFindingsSource(EvidenceSource):
    """Reads evidence from the existing scires.db findings table.

    Supports filtering by:
    - domain/keyword (via paper subjects or finding content)
    - recency (findings from the last N days)
    - confidence threshold
    - max items

    Logs retrieval statistics for auditability.
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        min_confidence: float = 0.6,
        recency_days: Optional[int] = None,
        keyword_filter: Optional[str] = None,
    ):
        self.db = db
        self.min_confidence = min_confidence
        self.recency_days = recency_days
        self.keyword_filter = keyword_filter

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        try:
            query, params = self._build_query(domain, limit)
            rows = self.db.execute(query, params).fetchall()
        except Exception as e:
            logger.warning("Failed to query findings table: %s", e)
            return []

        results = []
        skipped = 0
        mapping_errors = 0

        for row in rows:
            try:
                item = self._map_row(row)
                if item:
                    results.append(item)
                else:
                    skipped += 1
            except Exception as e:
                mapping_errors += 1
                logger.debug("Mapping error for finding %s: %s", row[0] if row else "?", e)

        logger.info(
            "ExistingFindingsSource: retrieved=%d, skipped=%d, mapping_errors=%d, domain=%s",
            len(results), skipped, mapping_errors, domain,
        )
        return results

    def _build_query(self, domain: str, limit: int) -> tuple[str, list]:
        """Build the SQL query with optional filters."""
        conditions = ["f.judge_verdict = 'accepted'", "f.confidence >= ?"]
        params: list = [self.min_confidence]

        # Recency filter
        if self.recency_days is not None:
            cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=self.recency_days)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            conditions.append("f.created_at >= ?")
            params.append(cutoff)

        # Domain/keyword filter: search in paper subjects, title, or finding content
        keyword = self.keyword_filter or domain
        if keyword and keyword != "cross-domain":
            conditions.append(
                "(p.subjects LIKE ? OR p.title LIKE ? OR f.content LIKE ?)"
            )
            like_term = f"%{keyword}%"
            params.extend([like_term, like_term, like_term])

        where = " AND ".join(conditions)
        params.append(limit)

        query = f"""
            SELECT f.finding_id, f.content, f.provenance_quote,
                   f.provenance_section, f.finding_type, f.confidence,
                   p.title, p.source, p.paper_id, p.arxiv_id, p.doi
            FROM findings f
            JOIN papers p ON f.paper_id = p.paper_id
            WHERE {where}
            ORDER BY f.confidence DESC
            LIMIT ?
        """
        return query, params

    def _map_row(self, row) -> Optional[EvidenceItem]:
        """Map a database row to an EvidenceItem, handling missing fields gracefully."""
        finding_id = row[0]
        content = row[1] or ""
        provenance_quote = row[2]
        finding_type = row[4] or "result"
        confidence = row[5] or 0.5
        paper_title = row[6] or "Unknown Paper"
        paper_source = row[7] or "unknown"
        paper_id = row[8] or ""
        arxiv_id = row[9]
        doi = row[10]

        # Derive the quote: prefer provenance_quote, fall back to content
        quote = provenance_quote or content[:300]
        if not quote or len(quote.strip()) < 5:
            return None  # skip findings with no usable text

        # Build citation string
        source_id_str = arxiv_id or doi or paper_id
        citation = f"{paper_source} {finding_type} ({source_id_str[:20]})"

        # Build source_id
        if arxiv_id:
            source_id = f"arxiv:{arxiv_id}"
        elif doi:
            source_id = f"doi:{doi}"
        else:
            source_id = f"finding:{finding_id}"

        return EvidenceItem(
            id=new_id(),
            source_type="finding",
            source_id=source_id,
            title=paper_title[:200],
            quote=quote[:500],
            citation=citation,
            relevance_score=float(confidence),
        )


class FutureRetrievalSource(EvidenceSource):
    """Stub for future literature search API integration (e.g., Semantic Scholar, OpenAlex)."""

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        logger.info("FutureRetrievalSource is a stub — returning empty evidence list")
        return []
