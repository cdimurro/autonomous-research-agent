"""Concept canonicalization and deduplication for KG entities.

Phase 10E-Prime: Transforms raw extracted entity strings into canonical
concept nodes, collapsing duplicates and filtering non-concepts (bare
values, measurements, generic fragments).

Design:
- Canonical identity = normalized name after stemming + synonym resolution
- Each canonical concept has aliases (original surface forms)
- Provenance preserved: which segments/papers mentioned each alias
- Value-entities (pure numbers, measurements) are filtered out
- Domain-specific synonym maps handle scientific naming variations
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from .db import Repository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Value-entity filters — these are NOT meaningful scientific concepts
# ---------------------------------------------------------------------------

_VALUE_PATTERNS = [
    re.compile(r'^[\d.,\s+\-/±×x^]+$'),                     # pure numbers
    re.compile(r'^\d+\.?\d*\s*%\s*\w*$'),                    # percentages (with optional trailing word)
    re.compile(r'^\d+\.?\d*\s*(nm|μm|mm|cm|m|kg|g|mg|μg|'    # measurements
               r'mL|L|mol|mmol|μmol|eV|meV|keV|MeV|GeV|K|'
               r'°C|GPa|MPa|kPa|W|kW|MW|mV|V|A|mA|Ω|Hz|'
               r'kHz|MHz|GHz|J|kJ|cal|kcal|Pa|bar|atm|'
               r'cm²|m²|cm³|m³|s|ms|μs|ns|min|hr|h)'
               r'(\s*\w*)?$', re.I),                         # with optional trailing word
    re.compile(r'^\d+\.?\d*\s*[×x]\s*10\^?\d+'),             # scientific notation
    re.compile(r'^\d+k?\s*\+/?-\s*\d+k?$', re.I),            # ranges like "260k +/- 10k"
    re.compile(r'^[<>≤≥~≈]\s*\d'),                            # comparison values
    re.compile(r'^\d+\.?\d*\s*(wt|vol|at)\s*%', re.I),       # composition percentages
]

# Short fragments that are too generic to be concepts
_MIN_NAME_LENGTH = 3
_GENERIC_NAMES = frozenset({
    "result", "results", "study", "method", "approach", "system",
    "sample", "experiment", "analysis", "data", "value", "effect",
    "model", "figure", "table", "reference", "device", "devices",
    "performance", "property", "properties", "material", "materials",
    "structure", "structures", "process", "technique", "application",
    "measurement", "observation", "finding", "conclusion",
})


def _is_value_entity(name: str) -> bool:
    """Return True if the name is a bare value/measurement, not a concept."""
    stripped = name.strip()
    if not stripped or len(stripped) < _MIN_NAME_LENGTH:
        return True
    for pat in _VALUE_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def _is_generic_entity(name: str) -> bool:
    """Return True if the name is too generic to be a useful concept."""
    return name.lower().strip() in _GENERIC_NAMES


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

# Simple stemming rules for scientific English
_STEM_SUFFIXES = [
    ("ies", "y"),     # efficiencies -> efficiency
    ("ses", "s"),     # analyses -> analysis (partial)
    ("es", "e"),      # devices -> device
    ("s", ""),        # cells -> cell
]

# Domain-specific synonym map: alias -> canonical
# Expanded for clean-energy domain
SYNONYM_MAP: dict[str, str] = {
    # Solar / photovoltaic
    "perovskite solar cells": "perovskite solar cell",
    "perovskite photovoltaic": "perovskite solar cell",
    "perovskite photovoltaics": "perovskite solar cell",
    "perovskite pv": "perovskite solar cell",
    "psc": "perovskite solar cell",
    "pscs": "perovskite solar cell",
    "all-perovskite tandem": "perovskite tandem solar cell",
    "all-perovskite tandem solar cells": "perovskite tandem solar cell",
    "all-perovskite tandem solar cell": "perovskite tandem solar cell",
    "perovskite-perovskite tandem": "perovskite tandem solar cell",
    "tandem solar cell": "tandem solar cell",
    "tandem solar cells": "tandem solar cell",
    "single-junction devices": "single-junction solar cell",
    "single-junction device": "single-junction solar cell",
    "single junction device": "single-junction solar cell",
    "silicon solar cell": "silicon solar cell",
    "silicon solar cells": "silicon solar cell",
    "si solar cell": "silicon solar cell",
    # Efficiency metrics
    "power conversion efficiency": "power conversion efficiency",
    "pce": "power conversion efficiency",
    "conversion efficiency": "power conversion efficiency",
    # Voltage
    "open-circuit voltage": "open-circuit voltage",
    "open circuit voltage": "open-circuit voltage",
    "voc": "open-circuit voltage",
    # Carbon capture
    "carbon capture": "carbon capture",
    "co2 capture": "carbon capture",
    "carbon dioxide capture": "carbon capture",
    "carbon capture and storage": "carbon capture and storage",
    "ccs": "carbon capture and storage",
    # MOFs
    "metal-organic framework": "metal-organic framework",
    "metal organic framework": "metal-organic framework",
    "mof": "metal-organic framework",
    "mofs": "metal-organic framework",
    # Battery
    "lithium-ion battery": "lithium-ion battery",
    "lithium ion battery": "lithium-ion battery",
    "li-ion battery": "lithium-ion battery",
    "lib": "lithium-ion battery",
    "solid-state battery": "solid-state battery",
    "solid state battery": "solid-state battery",
    "ssb": "solid-state battery",
    # Thermoelectric
    "thermoelectric": "thermoelectric material",
    "thermoelectric material": "thermoelectric material",
    "thermoelectric materials": "thermoelectric material",
    "zt": "thermoelectric figure of merit",
    "figure of merit": "thermoelectric figure of merit",
    # Hydrogen
    "hydrogen evolution reaction": "hydrogen evolution reaction",
    "her": "hydrogen evolution reaction",
    "water splitting": "water splitting",
    "electrolysis": "water electrolysis",
    "water electrolysis": "water electrolysis",
    # General
    "bandgap": "band gap",
    "band gap": "band gap",
    "band-gap": "band gap",
    "electron transport layer": "electron transport layer",
    "etl": "electron transport layer",
    "hole transport layer": "hole transport layer",
    "htl": "hole transport layer",
}


def _simple_stem(word: str) -> str:
    """Apply simple suffix stripping for scientific English."""
    w = word.lower().strip()
    for suffix, replacement in _STEM_SUFFIXES:
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            return w[:-len(suffix)] + replacement
    return w


def normalize_entity_name(name: str) -> str:
    """Normalize an entity name to its canonical form.

    Steps:
    1. Lowercase, strip whitespace
    2. Check synonym map
    3. Simple stemming for plurals
    4. Collapse multiple spaces
    """
    cleaned = name.lower().strip()
    # Collapse multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned)

    # Check synonym map first (exact match on cleaned form)
    if cleaned in SYNONYM_MAP:
        return SYNONYM_MAP[cleaned]

    # Try stemming and re-check
    words = cleaned.split()
    if len(words) >= 2:
        # Stem the last word (usually the noun)
        stemmed_last = _simple_stem(words[-1])
        candidate = ' '.join(words[:-1] + [stemmed_last])
        if candidate in SYNONYM_MAP:
            return SYNONYM_MAP[candidate]
        return candidate

    # Single word: stem it
    return _simple_stem(cleaned)


# ---------------------------------------------------------------------------
# Canonical concept
# ---------------------------------------------------------------------------

@dataclass
class CanonicalConcept:
    """A deduplicated concept node in the canonical graph."""
    canonical_name: str
    entity_type: str = "concept"
    description: str = ""
    confidence: float = 0.0
    aliases: list[str] = field(default_factory=list)
    source_entity_ids: list[str] = field(default_factory=list)
    source_paper_ids: set[str] = field(default_factory=set)
    source_segment_ids: set[str] = field(default_factory=set)
    mention_count: int = 0

    def to_dict(self) -> dict:
        return {
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type,
            "description": self.description,
            "confidence": round(self.confidence, 4),
            "aliases": sorted(set(self.aliases)),
            "source_entity_ids": self.source_entity_ids,
            "source_paper_ids": sorted(self.source_paper_ids),
            "source_segment_ids": sorted(self.source_segment_ids),
            "mention_count": self.mention_count,
            "cross_paper": len(self.source_paper_ids) > 1,
        }


# ---------------------------------------------------------------------------
# Canonicalization engine
# ---------------------------------------------------------------------------

@dataclass
class CanonicalizationStats:
    """Diagnostics from a canonicalization run."""
    total_entities: int = 0
    filtered_values: int = 0
    filtered_generic: int = 0
    remaining_entities: int = 0
    unique_canonical: int = 0
    duplicate_collapse_rate: float = 0.0
    cross_paper_concepts: int = 0
    top_clusters: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_entities": self.total_entities,
            "filtered_values": self.filtered_values,
            "filtered_generic": self.filtered_generic,
            "remaining_entities": self.remaining_entities,
            "unique_canonical": self.unique_canonical,
            "duplicate_collapse_rate": round(self.duplicate_collapse_rate, 4),
            "cross_paper_concepts": self.cross_paper_concepts,
            "top_clusters": self.top_clusters,
        }


class ConceptCanonicalizer:
    """Transforms raw KG entities into canonical concept nodes.

    Pipeline:
    1. Load entities from DB
    2. Filter value-entities and generic names
    3. Normalize names via synonym map + stemming
    4. Group by canonical name
    5. Select best representative per group (highest confidence, best description)
    6. Track aliases and provenance
    7. Optionally update DB with canonical names
    """

    def __init__(self, repo: Repository, synonym_map: Optional[dict[str, str]] = None):
        self.repo = repo
        self.synonyms = synonym_map or dict(SYNONYM_MAP)

    def canonicalize(
        self,
        domain: str = "",
        limit: int = 2000,
        update_db: bool = False,
    ) -> tuple[dict[str, CanonicalConcept], CanonicalizationStats]:
        """Run canonicalization on all entities.

        Returns:
            (canonical_map, stats) where canonical_map maps
            canonical_name -> CanonicalConcept
        """
        entities = self.repo.list_kg_entities(domain=domain, limit=limit)
        stats = CanonicalizationStats(total_entities=len(entities))

        # Step 1: Filter
        filtered: list[dict] = []
        for ent in entities:
            name = ent.get("name", "")
            if _is_value_entity(name):
                stats.filtered_values += 1
                continue
            if _is_generic_entity(name):
                stats.filtered_generic += 1
                continue
            filtered.append(ent)

        stats.remaining_entities = len(filtered)

        # Step 2: Normalize and group
        groups: dict[str, list[dict]] = {}
        for ent in filtered:
            canonical = normalize_entity_name(ent.get("name", ""))
            if not canonical or len(canonical) < _MIN_NAME_LENGTH:
                continue
            groups.setdefault(canonical, []).append(ent)

        # Step 3: Build canonical concepts
        canonical_map: dict[str, CanonicalConcept] = {}
        for cname, ents in groups.items():
            # Pick best representative: highest confidence, longest description
            best = max(ents, key=lambda e: (
                e.get("confidence", 0),
                len(e.get("description", "")),
            ))

            concept = CanonicalConcept(
                canonical_name=cname,
                entity_type=best.get("entity_type", "concept"),
                description=best.get("description", ""),
                confidence=max(e.get("confidence", 0) for e in ents),
                aliases=list({e.get("name", "") for e in ents}),
                source_entity_ids=[e.get("id", "") for e in ents],
                source_paper_ids={e.get("paper_id", "") for e in ents if e.get("paper_id")},
                source_segment_ids={e.get("segment_id", "") for e in ents if e.get("segment_id")},
                mention_count=len(ents),
            )
            canonical_map[cname] = concept

        stats.unique_canonical = len(canonical_map)
        if stats.remaining_entities > 0:
            stats.duplicate_collapse_rate = 1.0 - (
                stats.unique_canonical / stats.remaining_entities
            )

        stats.cross_paper_concepts = sum(
            1 for c in canonical_map.values() if len(c.source_paper_ids) > 1
        )

        # Top clusters by mention count
        top = sorted(canonical_map.values(), key=lambda c: -c.mention_count)[:15]
        stats.top_clusters = [
            {
                "name": c.canonical_name,
                "mentions": c.mention_count,
                "aliases": sorted(set(c.aliases))[:5],
                "papers": len(c.source_paper_ids),
                "type": c.entity_type,
            }
            for c in top
        ]

        # Step 4: Optionally update DB canonical_name column
        if update_db:
            self._update_db_canonical_names(filtered, canonical_map)

        logger.info(
            "Canonicalization: total=%d filtered=%d remaining=%d "
            "canonical=%d collapse=%.1f%% cross_paper=%d",
            stats.total_entities,
            stats.filtered_values + stats.filtered_generic,
            stats.remaining_entities,
            stats.unique_canonical,
            stats.duplicate_collapse_rate * 100,
            stats.cross_paper_concepts,
        )

        return canonical_map, stats

    def _update_db_canonical_names(
        self,
        entities: list[dict],
        canonical_map: dict[str, CanonicalConcept],
    ) -> int:
        """Update canonical_name in bt_kg_entities to match canonicalized forms."""
        updated = 0
        for ent in entities:
            name = ent.get("name", "")
            canonical = normalize_entity_name(name)
            if canonical and canonical != ent.get("canonical_name", ""):
                self.repo.update_entity_canonical_name(ent["id"], canonical)
                updated += 1
        return updated

    def build_entity_id_to_canonical(
        self,
        canonical_map: dict[str, CanonicalConcept],
    ) -> dict[str, str]:
        """Build mapping from raw entity_id to canonical_name."""
        mapping: dict[str, str] = {}
        for cname, concept in canonical_map.items():
            for eid in concept.source_entity_ids:
                mapping[eid] = cname
        return mapping


# ---------------------------------------------------------------------------
# Canonical graph adapter for reasoning
# ---------------------------------------------------------------------------

@dataclass
class CanonicalEdge:
    """An edge in the canonical concept graph."""
    source_canonical: str
    target_canonical: str
    relation_type: str
    confidence: float
    source_papers: set[str] = field(default_factory=set)
    is_cross_paper: bool = False
    description: str = ""


class CanonicalGraph:
    """A concept-level graph built from canonicalized entities and raw relations.

    Nodes are canonical concepts (deduplicated).
    Edges are relations mapped through entity_id -> canonical_name.
    Cross-paper edges are explicitly tagged.
    """

    def __init__(self):
        self.concepts: dict[str, CanonicalConcept] = {}
        self.edges: list[CanonicalEdge] = []
        self._adjacency: dict[str, list[CanonicalEdge]] = {}

    @property
    def node_count(self) -> int:
        return len(self.concepts)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def cross_paper_edge_count(self) -> int:
        return sum(1 for e in self.edges if e.is_cross_paper)

    def build(
        self,
        canonical_map: dict[str, CanonicalConcept],
        entity_id_to_canonical: dict[str, str],
        relations: list[dict],
    ) -> None:
        """Build the canonical graph from concepts and raw relations."""
        self.concepts = dict(canonical_map)

        seen_edges: set[tuple[str, str, str]] = set()

        for rel in relations:
            src_id = rel.get("source_entity_id", "")
            tgt_id = rel.get("target_entity_id", "")
            src_canonical = entity_id_to_canonical.get(src_id)
            tgt_canonical = entity_id_to_canonical.get(tgt_id)

            if not src_canonical or not tgt_canonical:
                continue
            if src_canonical == tgt_canonical:
                continue  # self-loops after canonicalization

            rtype = rel.get("relation_type", "related_to")
            edge_key = (src_canonical, tgt_canonical, rtype)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            # Determine cross-paper status
            src_papers = self.concepts[src_canonical].source_paper_ids if src_canonical in self.concepts else set()
            tgt_papers = self.concepts[tgt_canonical].source_paper_ids if tgt_canonical in self.concepts else set()
            is_cross = bool(src_papers and tgt_papers and not src_papers.intersection(tgt_papers))

            edge = CanonicalEdge(
                source_canonical=src_canonical,
                target_canonical=tgt_canonical,
                relation_type=rtype,
                confidence=rel.get("confidence", 0.5),
                source_papers=src_papers | tgt_papers,
                is_cross_paper=is_cross,
                description=rel.get("description", ""),
            )
            self.edges.append(edge)
            self._adjacency.setdefault(src_canonical, []).append(edge)
            # Undirected for traversal
            reverse_edge = CanonicalEdge(
                source_canonical=tgt_canonical,
                target_canonical=src_canonical,
                relation_type=rtype,
                confidence=edge.confidence,
                source_papers=edge.source_papers,
                is_cross_paper=edge.is_cross_paper,
                description=edge.description,
            )
            self._adjacency.setdefault(tgt_canonical, []).append(reverse_edge)

    def get_neighbors(self, canonical_name: str) -> list[CanonicalEdge]:
        """Return all edges from a canonical concept."""
        return self._adjacency.get(canonical_name, [])

    def get_connected_components(self) -> list[set[str]]:
        """Return connected components of the concept graph."""
        visited: set[str] = set()
        components: list[set[str]] = []

        for name in self.concepts:
            if name in visited:
                continue
            component: set[str] = set()
            queue = [name]
            while queue:
                current = queue.pop()
                if current in visited:
                    continue
                visited.add(current)
                component.add(current)
                for edge in self.get_neighbors(current):
                    target = edge.target_canonical
                    if target not in visited and target in self.concepts:
                        queue.append(target)
            components.append(component)

        return sorted(components, key=len, reverse=True)

    def quality_metrics(self) -> dict:
        """Compute graph quality metrics."""
        components = self.get_connected_components()
        cross_paper_concepts = sum(
            1 for c in self.concepts.values() if len(c.source_paper_ids) > 1
        )
        confidences = [c.confidence for c in self.concepts.values()]
        edge_confs = [e.confidence for e in self.edges]

        metrics = {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "cross_paper_edges": self.cross_paper_edge_count,
            "connected_components": len(components),
            "largest_component": len(components[0]) if components else 0,
            "component_sizes": [len(c) for c in components[:10]],
            "cross_paper_concepts": cross_paper_concepts,
            "relation_density": round(self.edge_count / max(1, self.node_count), 3),
        }
        if confidences:
            metrics["mean_concept_confidence"] = round(sum(confidences) / len(confidences), 4)
        if edge_confs:
            metrics["mean_edge_confidence"] = round(sum(edge_confs) / len(edge_confs), 4)
        return metrics
