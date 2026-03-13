"""Cross-paper subgraph construction for evidence neighborhoods.

Phase 10E-Prime: Builds compact, topic-focused subgraphs from the
canonical concept graph. Subgraphs serve as structured inputs to
graph-conditioned generation and grounding validation.

A subgraph is a small neighborhood of concepts and relations around
a hypothesis theme, prioritizing:
- Cross-paper connections (the unique KG advantage)
- Mechanistic coherence (causal chains, not random associations)
- Source diversity (multi-paper support)
- Confidence (trustworthy edges)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .kg_canonicalization import CanonicalGraph, CanonicalConcept, CanonicalEdge
from .models import EvidenceItem, new_id

logger = logging.getLogger(__name__)

# Relation types that form mechanistic chains (vs merely associative)
_MECHANISTIC_RELATIONS = frozenset({
    "causes", "inhibits", "enhances", "enables", "catalyzes",
    "produces", "degrades", "requires", "composed_of",
})


@dataclass
class SubgraphNode:
    """A node in an evidence subgraph."""
    canonical_name: str
    entity_type: str = "concept"
    confidence: float = 0.0
    paper_count: int = 0
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.canonical_name,
            "type": self.entity_type,
            "confidence": round(self.confidence, 3),
            "papers": self.paper_count,
            "description": self.description[:100],
        }


@dataclass
class SubgraphEdge:
    """An edge in an evidence subgraph."""
    source: str
    target: str
    relation_type: str
    confidence: float = 0.0
    is_cross_paper: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation_type,
            "confidence": round(self.confidence, 3),
            "cross_paper": self.is_cross_paper,
        }


@dataclass
class EvidenceSubgraph:
    """A compact evidence neighborhood around a topic.

    Small enough for prompt inclusion, rich enough for structural reasoning.
    """
    topic: str = ""
    nodes: list[SubgraphNode] = field(default_factory=list)
    edges: list[SubgraphEdge] = field(default_factory=list)
    cross_paper_edges: int = 0
    mechanistic_edges: int = 0
    paper_ids: set[str] = field(default_factory=set)
    confidence_mean: float = 0.0

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "cross_paper_edges": self.cross_paper_edges,
            "mechanistic_edges": self.mechanistic_edges,
            "paper_count": len(self.paper_ids),
            "confidence_mean": round(self.confidence_mean, 4),
        }

    def to_evidence_item(self) -> EvidenceItem:
        """Convert subgraph to a single EvidenceItem for retrieval integration."""
        node_names = [n.canonical_name for n in self.nodes[:6]]
        edge_descs = []
        for e in self.edges[:5]:
            edge_descs.append(f"{e.source} [{e.relation_type}] {e.target}")

        title = f"Subgraph: {self.topic} ({self.node_count} concepts, {len(self.paper_ids)} papers)"
        quote_parts = [
            f"Concepts: {', '.join(node_names)}",
            f"Relations: {'; '.join(edge_descs)}",
        ]
        if self.cross_paper_edges:
            quote_parts.append(f"Cross-paper connections: {self.cross_paper_edges}")

        return EvidenceItem(
            id=new_id(),
            source_type="kg_subgraph",
            source_id=f"subgraph_{self.topic[:30]}",
            title=title,
            quote=". ".join(quote_parts),
            citation=f"KG subgraph ({len(self.paper_ids)} papers)",
            relevance_score=self.confidence_mean,
        )

    def to_prompt_block(self) -> str:
        """Format subgraph as a compact prompt block for generation.

        Designed to be small enough for context window inclusion while
        preserving structural information.
        """
        lines = [f"GRAPH NEIGHBORHOOD: {self.topic}"]
        lines.append(f"  Concepts ({self.node_count}):")
        for n in self.nodes[:8]:
            papers_tag = f" [{n.paper_count}p]" if n.paper_count > 1 else ""
            lines.append(f"    - {n.canonical_name} ({n.entity_type}){papers_tag}")
        lines.append(f"  Relations ({self.edge_count}):")
        for e in self.edges[:8]:
            xp = " [CROSS-PAPER]" if e.is_cross_paper else ""
            lines.append(f"    - {e.source} [{e.relation_type}] {e.target}{xp}")
        if self.cross_paper_edges:
            lines.append(f"  Cross-paper connections: {self.cross_paper_edges}")
        lines.append(f"  Papers involved: {len(self.paper_ids)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Subgraph builder
# ---------------------------------------------------------------------------

class SubgraphBuilder:
    """Builds compact evidence subgraphs from the canonical concept graph.

    Strategies:
    1. Seed expansion: Start from seed concepts, expand via BFS
    2. Topic matching: Find concepts matching topic keywords, build neighborhood
    3. Cross-paper focus: Prioritize edges that bridge papers
    """

    def __init__(
        self,
        graph: CanonicalGraph,
        max_nodes: int = 12,
        max_edges: int = 20,
        prefer_cross_paper: bool = True,
        prefer_mechanistic: bool = True,
    ):
        self.graph = graph
        self.max_nodes = max_nodes
        self.max_edges = max_edges
        self.prefer_cross_paper = prefer_cross_paper
        self.prefer_mechanistic = prefer_mechanistic

    def build_from_seeds(
        self,
        seed_concepts: list[str],
        topic: str = "",
        max_hops: int = 2,
    ) -> EvidenceSubgraph:
        """Build a subgraph by expanding from seed concepts via BFS."""
        subgraph = EvidenceSubgraph(topic=topic or ", ".join(seed_concepts[:3]))

        # Collect nodes via BFS
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(s, 0) for s in seed_concepts if s in self.graph.concepts]
        collected_nodes: list[str] = []

        while queue and len(collected_nodes) < self.max_nodes:
            current, depth = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            collected_nodes.append(current)

            if depth < max_hops:
                neighbors = self.graph.get_neighbors(current)
                # Sort: cross-paper first, then mechanistic, then by confidence
                neighbors.sort(key=lambda e: (
                    -(1 if e.is_cross_paper and self.prefer_cross_paper else 0),
                    -(1 if e.relation_type in _MECHANISTIC_RELATIONS and self.prefer_mechanistic else 0),
                    -e.confidence,
                ))
                for edge in neighbors:
                    target = edge.target_canonical
                    if target not in visited and target in self.graph.concepts:
                        queue.append((target, depth + 1))

        # Build SubgraphNodes
        for cname in collected_nodes:
            concept = self.graph.concepts.get(cname)
            if concept:
                subgraph.nodes.append(SubgraphNode(
                    canonical_name=cname,
                    entity_type=concept.entity_type,
                    confidence=concept.confidence,
                    paper_count=len(concept.source_paper_ids),
                    description=concept.description,
                ))
                subgraph.paper_ids.update(concept.source_paper_ids)

        # Collect edges between collected nodes
        node_set = set(collected_nodes)
        seen_edges: set[tuple[str, str, str]] = set()

        for cname in collected_nodes:
            for edge in self.graph.get_neighbors(cname):
                if edge.target_canonical in node_set:
                    ekey = tuple(sorted([edge.source_canonical, edge.target_canonical])) + (edge.relation_type,)
                    if ekey not in seen_edges and len(subgraph.edges) < self.max_edges:
                        seen_edges.add(ekey)
                        sg_edge = SubgraphEdge(
                            source=edge.source_canonical,
                            target=edge.target_canonical,
                            relation_type=edge.relation_type,
                            confidence=edge.confidence,
                            is_cross_paper=edge.is_cross_paper,
                            description=edge.description,
                        )
                        subgraph.edges.append(sg_edge)
                        if edge.is_cross_paper:
                            subgraph.cross_paper_edges += 1
                        if edge.relation_type in _MECHANISTIC_RELATIONS:
                            subgraph.mechanistic_edges += 1

        # Compute confidence
        all_confs = [n.confidence for n in subgraph.nodes] + [e.confidence for e in subgraph.edges]
        if all_confs:
            subgraph.confidence_mean = sum(all_confs) / len(all_confs)

        return subgraph

    def build_from_topic(
        self,
        topic: str,
        max_hops: int = 2,
    ) -> EvidenceSubgraph:
        """Build a subgraph by finding concepts matching topic keywords."""
        topic_words = set(topic.lower().split())
        # Find seed concepts that match topic words
        seeds: list[tuple[float, str]] = []
        for cname, concept in self.graph.concepts.items():
            name_words = set(cname.split())
            overlap = len(topic_words & name_words)
            if overlap > 0:
                score = overlap / max(1, len(topic_words))
                seeds.append((score, cname))

        seeds.sort(reverse=True)
        seed_names = [s[1] for s in seeds[:5]]

        if not seed_names:
            # Fallback: use highest-confidence concepts
            by_conf = sorted(self.graph.concepts.items(), key=lambda x: -x[1].confidence)
            seed_names = [c[0] for c in by_conf[:3]]

        return self.build_from_seeds(seed_names, topic=topic, max_hops=max_hops)

    def build_cross_paper_subgraph(
        self,
        min_confidence: float = 0.3,
    ) -> EvidenceSubgraph:
        """Build a subgraph focused on cross-paper connections."""
        # Start from cross-paper edges
        cross_paper_concepts: set[str] = set()
        for edge in self.graph.edges:
            if edge.is_cross_paper and edge.confidence >= min_confidence:
                cross_paper_concepts.add(edge.source_canonical)
                cross_paper_concepts.add(edge.target_canonical)

        if not cross_paper_concepts:
            # Fallback: concepts appearing in multiple papers
            for cname, concept in self.graph.concepts.items():
                if len(concept.source_paper_ids) > 1:
                    cross_paper_concepts.add(cname)

        seeds = list(cross_paper_concepts)[:8]
        return self.build_from_seeds(
            seeds, topic="cross-paper synthesis", max_hops=1,
        )
