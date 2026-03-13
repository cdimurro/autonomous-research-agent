"""Multi-hop graph reasoning and cross-segment synthesis.

Phase 10E: Extends the KG beyond flat entity lookup to support:
1. Bounded multi-hop path traversal (2-3 hops)
2. Cross-paper evidence chain synthesis
3. Path confidence computation
4. Inspectable reasoning traces

Phase 10E-Prime: Adds canonical graph reasoning that operates on
deduplicated concept nodes, enabling real cross-paper path discovery.

The value proposition: surface structural connections that exist
across papers but are invisible to flat findings retrieval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .db import Repository
from .models import EvidenceItem, new_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GraphNode:
    """An entity in the reasoning graph."""
    entity_id: str
    name: str
    entity_type: str
    paper_id: str
    segment_id: str
    confidence: float
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "type": self.entity_type,
            "paper_id": self.paper_id,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class GraphEdge:
    """A relation in the reasoning graph."""
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str
    paper_id: str
    confidence: float
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "relation_id": self.relation_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.relation_type,
            "paper_id": self.paper_id,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class ReasoningPath:
    """A multi-hop path through the knowledge graph.

    Example 2-hop path:
      Perovskite --[enhances]--> Electron Transport --[enables]--> High Efficiency
      paper_ids: {paper_A, paper_B} (cross-paper!)
    """
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    hop_count: int = 0
    path_confidence: float = 0.0
    is_cross_paper: bool = False
    paper_ids: set[str] = field(default_factory=set)
    reasoning_trace: str = ""

    def to_dict(self) -> dict:
        return {
            "hop_count": self.hop_count,
            "path_confidence": round(self.path_confidence, 4),
            "is_cross_paper": self.is_cross_paper,
            "paper_count": len(self.paper_ids),
            "paper_ids": sorted(self.paper_ids),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "reasoning_trace": self.reasoning_trace,
        }

    def to_evidence_item(self) -> EvidenceItem:
        """Convert this path into a standard EvidenceItem for pipeline use."""
        # Build a structured quote from the path
        parts = []
        for i, edge in enumerate(self.edges):
            src = self.nodes[i] if i < len(self.nodes) else None
            tgt = self.nodes[i + 1] if i + 1 < len(self.nodes) else None
            src_name = src.name if src else "?"
            tgt_name = tgt.name if tgt else "?"
            parts.append(f"{src_name} [{edge.relation_type}] {tgt_name}")

        quote = " → ".join(parts)
        if self.reasoning_trace:
            quote += f". Inference: {self.reasoning_trace}"

        title_parts = [n.name for n in self.nodes[:3]]
        title = " → ".join(title_parts)
        if len(self.nodes) > 3:
            title += f" (+{len(self.nodes) - 3} more)"

        papers = sorted(self.paper_ids)
        citation = f"KG {self.hop_count}-hop path ({len(papers)} papers)"

        return EvidenceItem(
            id=new_id(),
            source_type="graph_path",
            source_id=f"path:{':'.join(papers[:3])}",
            title=title[:200],
            quote=quote[:500],
            citation=citation,
            relevance_score=self.path_confidence,
        )


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

class KGGraphBuilder:
    """Builds an in-memory graph from the KG tables for reasoning."""

    def __init__(self, repo: Repository):
        self.repo = repo
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._adj: dict[str, list[GraphEdge]] = {}  # entity_id -> edges

    def load(self, domain: str = "", limit: int = 500) -> None:
        """Load entities and relations from the database."""
        entities = self.repo.list_kg_entities(domain=domain, limit=limit)
        for e in entities:
            node = GraphNode(
                entity_id=e["id"],
                name=e.get("name", ""),
                entity_type=e.get("entity_type", "concept"),
                paper_id=e.get("paper_id", ""),
                segment_id=e.get("segment_id", ""),
                confidence=float(e.get("confidence", 0.5)),
                description=e.get("description", ""),
            )
            self._nodes[node.entity_id] = node

        # Load relations for all loaded entities
        for eid in list(self._nodes.keys()):
            rels = self.repo.get_kg_relations_for_entity(eid)
            for r in rels:
                edge = GraphEdge(
                    relation_id=r["id"],
                    source_id=r["source_entity_id"],
                    target_id=r["target_entity_id"],
                    relation_type=r.get("relation_type", "related_to"),
                    paper_id=r.get("paper_id", ""),
                    confidence=float(r.get("confidence", 0.5)),
                    description=r.get("description", ""),
                )
                if edge.relation_id not in {e.relation_id for e in self._edges}:
                    self._edges.append(edge)
                    self._adj.setdefault(edge.source_id, []).append(edge)
                    self._adj.setdefault(edge.target_id, []).append(edge)

        logger.info(
            "KGGraphBuilder: loaded %d nodes, %d edges for domain=%s",
            len(self._nodes), len(self._edges), domain,
        )

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def get_node(self, entity_id: str) -> Optional[GraphNode]:
        return self._nodes.get(entity_id)

    def get_neighbors(self, entity_id: str) -> list[tuple[GraphEdge, GraphNode]]:
        """Get immediate neighbors of an entity."""
        result = []
        for edge in self._adj.get(entity_id, []):
            other_id = edge.target_id if edge.source_id == entity_id else edge.source_id
            other = self._nodes.get(other_id)
            if other:
                result.append((edge, other))
        return result


# ---------------------------------------------------------------------------
# Multi-hop path finder
# ---------------------------------------------------------------------------

class MultiHopReasoner:
    """Finds multi-hop reasoning paths through the knowledge graph.

    Supports 1-hop, 2-hop, and 3-hop bounded paths.
    Prioritizes cross-paper paths and filters low-confidence chains.
    """

    def __init__(
        self,
        graph: KGGraphBuilder,
        max_hops: int = 2,
        min_path_confidence: float = 0.2,
        prefer_cross_paper: bool = True,
    ):
        self.graph = graph
        self.max_hops = min(max_hops, 3)  # hard cap at 3
        self.min_path_confidence = min_path_confidence
        self.prefer_cross_paper = prefer_cross_paper

    def find_paths(
        self, start_entity_id: str = "", domain: str = "", limit: int = 20,
    ) -> list[ReasoningPath]:
        """Find reasoning paths starting from an entity or across the graph."""
        all_paths: list[ReasoningPath] = []

        if start_entity_id:
            # Find paths from a specific entity
            start = self.graph.get_node(start_entity_id)
            if start:
                all_paths.extend(self._bfs_paths(start))
        else:
            # Find interesting paths across the whole graph
            for node in list(self.graph._nodes.values()):
                paths = self._bfs_paths(node)
                all_paths.extend(paths)
                if len(all_paths) >= limit * 3:
                    break

        # Filter and rank
        valid = [p for p in all_paths if p.path_confidence >= self.min_path_confidence]

        # Sort: cross-paper first if preferred, then by confidence
        def _sort_key(p: ReasoningPath) -> tuple:
            cross_bonus = 1.0 if (self.prefer_cross_paper and p.is_cross_paper) else 0.0
            return (-cross_bonus, -p.path_confidence, -p.hop_count)

        valid.sort(key=_sort_key)
        # Deduplicate by node set
        seen: set[frozenset[str]] = set()
        deduped: list[ReasoningPath] = []
        for p in valid:
            key = frozenset(n.entity_id for n in p.nodes)
            if key not in seen:
                seen.add(key)
                deduped.append(p)
        return deduped[:limit]

    def _bfs_paths(self, start: GraphNode) -> list[ReasoningPath]:
        """BFS from start node up to max_hops, collecting paths."""
        paths: list[ReasoningPath] = []

        # State: (current_node, path_nodes, path_edges, visited_ids)
        queue: list[tuple[GraphNode, list[GraphNode], list[GraphEdge], set[str]]] = [
            (start, [start], [], {start.entity_id}),
        ]

        while queue:
            current, path_nodes, path_edges, visited = queue.pop(0)
            hop_count = len(path_edges)

            # Yield paths of length >= 2 hops (1-hop is trivial)
            if hop_count >= 2:
                path = self._build_path(path_nodes, path_edges)
                if path.path_confidence >= self.min_path_confidence:
                    paths.append(path)

            if hop_count >= self.max_hops:
                continue

            # Expand neighbors
            for edge, neighbor in self.graph.get_neighbors(current.entity_id):
                if neighbor.entity_id not in visited:
                    queue.append((
                        neighbor,
                        path_nodes + [neighbor],
                        path_edges + [edge],
                        visited | {neighbor.entity_id},
                    ))

        return paths

    def _build_path(self, nodes: list[GraphNode], edges: list[GraphEdge]) -> ReasoningPath:
        """Build a ReasoningPath from nodes and edges."""
        paper_ids = {n.paper_id for n in nodes if n.paper_id}
        paper_ids |= {e.paper_id for e in edges if e.paper_id}

        # Path confidence: product of node and edge confidences (geometric mean)
        all_confs = [n.confidence for n in nodes] + [e.confidence for e in edges]
        if all_confs:
            # Geometric mean
            from functools import reduce
            import operator
            product = reduce(operator.mul, all_confs, 1.0)
            geo_mean = product ** (1.0 / len(all_confs))
        else:
            geo_mean = 0.0

        # Build reasoning trace
        trace_parts = []
        for i, edge in enumerate(edges):
            src = nodes[i].name if i < len(nodes) else "?"
            tgt = nodes[i + 1].name if i + 1 < len(nodes) else "?"
            trace_parts.append(f"{src} {edge.relation_type} {tgt}")
        reasoning = ", therefore ".join(trace_parts)

        is_cross_paper = len(paper_ids) > 1

        return ReasoningPath(
            nodes=list(nodes),
            edges=list(edges),
            hop_count=len(edges),
            path_confidence=round(geo_mean, 4),
            is_cross_paper=is_cross_paper,
            paper_ids=paper_ids,
            reasoning_trace=reasoning,
        )

    def find_cross_paper_paths(self, domain: str = "", limit: int = 10) -> list[ReasoningPath]:
        """Find only cross-paper reasoning paths."""
        all_paths = self.find_paths(domain=domain, limit=limit * 5)
        cross = [p for p in all_paths if p.is_cross_paper]
        return cross[:limit]

    def paths_to_evidence(self, paths: list[ReasoningPath]) -> list[EvidenceItem]:
        """Convert reasoning paths to EvidenceItems for pipeline use."""
        return [p.to_evidence_item() for p in paths]


# ---------------------------------------------------------------------------
# Cross-paper synthesis
# ---------------------------------------------------------------------------

@dataclass
class SynthesisLink:
    """A synthesized connection between entities from different papers."""
    source_entity: GraphNode
    target_entity: GraphNode
    via_edges: list[GraphEdge]
    source_paper_id: str
    target_paper_id: str
    synthesis_confidence: float
    explanation: str

    def to_dict(self) -> dict:
        return {
            "source": self.source_entity.name,
            "target": self.target_entity.name,
            "source_paper": self.source_paper_id,
            "target_paper": self.target_paper_id,
            "confidence": round(self.synthesis_confidence, 4),
            "explanation": self.explanation,
        }

    def to_evidence_item(self) -> EvidenceItem:
        """Convert to EvidenceItem."""
        return EvidenceItem(
            id=new_id(),
            source_type="kg_synthesis",
            source_id=f"synth:{self.source_paper_id[:8]}:{self.target_paper_id[:8]}",
            title=f"{self.source_entity.name} ↔ {self.target_entity.name} (cross-paper)",
            quote=self.explanation[:500],
            citation=f"KG synthesis ({self.source_paper_id[:16]} + {self.target_paper_id[:16]})",
            relevance_score=self.synthesis_confidence,
        )


class CrossPaperSynthesizer:
    """Synthesizes connections across papers using graph structure.

    Finds entities from different papers that connect through shared
    intermediate concepts, producing traceable synthesis links.
    """

    def __init__(
        self,
        graph: KGGraphBuilder,
        min_confidence: float = 0.25,
    ):
        self.graph = graph
        self.min_confidence = min_confidence

    def synthesize(self, domain: str = "", limit: int = 10) -> list[SynthesisLink]:
        """Find cross-paper synthesis links."""
        links: list[SynthesisLink] = []

        # Group entities by paper
        by_paper: dict[str, list[GraphNode]] = {}
        for node in self.graph._nodes.values():
            if node.paper_id:
                by_paper.setdefault(node.paper_id, []).append(node)

        paper_ids = list(by_paper.keys())
        if len(paper_ids) < 2:
            return []

        # For each pair of papers, find shared-concept bridges
        for i, pid1 in enumerate(paper_ids):
            for pid2 in paper_ids[i + 1:]:
                paper_links = self._find_bridges(
                    by_paper[pid1], by_paper[pid2], pid1, pid2,
                )
                links.extend(paper_links)
                if len(links) >= limit * 3:
                    break
            if len(links) >= limit * 3:
                break

        # Filter and rank
        valid = [l for l in links if l.synthesis_confidence >= self.min_confidence]
        valid.sort(key=lambda l: -l.synthesis_confidence)
        return valid[:limit]

    def _find_bridges(
        self,
        nodes_a: list[GraphNode],
        nodes_b: list[GraphNode],
        paper_a: str,
        paper_b: str,
    ) -> list[SynthesisLink]:
        """Find bridges between entities from two papers."""
        bridges: list[SynthesisLink] = []

        # Check for shared canonical names (same concept in different papers)
        names_a = {n.name.lower(): n for n in nodes_a}
        names_b = {n.name.lower(): n for n in nodes_b}
        shared = set(names_a.keys()) & set(names_b.keys())

        for name in shared:
            na, nb = names_a[name], names_b[name]
            conf = min(na.confidence, nb.confidence)
            bridges.append(SynthesisLink(
                source_entity=na,
                target_entity=nb,
                via_edges=[],
                source_paper_id=paper_a,
                target_paper_id=paper_b,
                synthesis_confidence=conf,
                explanation=(
                    f"'{na.name}' appears in both papers. "
                    f"Paper {paper_a[:16]} describes it as: {na.description[:100]}. "
                    f"Paper {paper_b[:16]} describes it as: {nb.description[:100]}. "
                    f"Cross-paper corroboration strengthens evidence."
                ),
            ))

        # Check for 1-hop bridges via shared neighbors
        neighbors_a: dict[str, tuple[GraphNode, GraphEdge]] = {}
        for na in nodes_a:
            for edge, neighbor in self.graph.get_neighbors(na.entity_id):
                neighbors_a[neighbor.name.lower()] = (na, edge)

        for nb in nodes_b:
            for edge_b, neighbor_b in self.graph.get_neighbors(nb.entity_id):
                key = neighbor_b.name.lower()
                if key in neighbors_a:
                    na, edge_a = neighbors_a[key]
                    if na.paper_id != nb.paper_id:
                        conf = min(na.confidence, nb.confidence, edge_a.confidence, edge_b.confidence)
                        bridges.append(SynthesisLink(
                            source_entity=na,
                            target_entity=nb,
                            via_edges=[edge_a, edge_b],
                            source_paper_id=paper_a,
                            target_paper_id=paper_b,
                            synthesis_confidence=conf * 0.9,  # slight penalty for indirection
                            explanation=(
                                f"'{na.name}' ({paper_a[:16]}) [{edge_a.relation_type}] "
                                f"'{neighbor_b.name}' [{edge_b.relation_type}] "
                                f"'{nb.name}' ({paper_b[:16]}). "
                                f"Cross-paper bridge via shared concept."
                            ),
                        ))

        return bridges

    def synthesis_to_evidence(self, links: list[SynthesisLink]) -> list[EvidenceItem]:
        """Convert synthesis links to EvidenceItems."""
        return [l.to_evidence_item() for l in links]


# ---------------------------------------------------------------------------
# Canonical graph reasoning (Phase 10E-Prime)
# ---------------------------------------------------------------------------

@dataclass
class CanonicalReasoningPath:
    """A multi-hop path through the canonical concept graph.

    Unlike ReasoningPath which uses raw entity IDs, this operates on
    deduplicated canonical concept names, enabling real cross-paper
    path discovery after canonicalization.
    """
    concepts: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    hop_count: int = 0
    path_confidence: float = 0.0
    is_cross_paper: bool = False
    paper_ids: set[str] = field(default_factory=set)
    reasoning_trace: str = ""
    template_match: str = ""  # e.g., "material → property → device"

    def to_dict(self) -> dict:
        return {
            "concepts": self.concepts,
            "relations": self.relations,
            "hop_count": self.hop_count,
            "path_confidence": round(self.path_confidence, 4),
            "is_cross_paper": self.is_cross_paper,
            "paper_count": len(self.paper_ids),
            "reasoning_trace": self.reasoning_trace,
            "template_match": self.template_match,
        }

    def to_evidence_item(self) -> EvidenceItem:
        """Convert to EvidenceItem for pipeline integration."""
        parts = []
        for i, rel in enumerate(self.relations):
            src = self.concepts[i] if i < len(self.concepts) else "?"
            tgt = self.concepts[i + 1] if i + 1 < len(self.concepts) else "?"
            parts.append(f"{src} [{rel}] {tgt}")

        quote = " → ".join(parts)
        xp_tag = " (CROSS-PAPER)" if self.is_cross_paper else ""
        if self.reasoning_trace:
            quote += f". {self.reasoning_trace}"

        title = " → ".join(self.concepts[:4])
        if len(self.concepts) > 4:
            title += f" (+{len(self.concepts) - 4})"
        title += xp_tag

        return EvidenceItem(
            id=new_id(),
            source_type="graph_path",
            source_id=f"cpath:{'→'.join(c[:12] for c in self.concepts[:3])}",
            title=title[:200],
            quote=quote[:500],
            citation=f"KG canonical {self.hop_count}-hop ({len(self.paper_ids)} papers)",
            relevance_score=self.path_confidence,
        )


# Scientific motif templates for path scoring
PATH_TEMPLATES: dict[str, list[set[str]]] = {
    "material → property → device": [
        {"material", "compound", "structure"},
        {"property", "metric", "phenomenon"},
        {"device", "technology"},
    ],
    "catalyst → mechanism → efficiency": [
        {"material", "compound"},
        {"mechanism", "process"},
        {"property", "metric"},
    ],
    "structure → transport → performance": [
        {"structure", "material"},
        {"mechanism", "process", "phenomenon"},
        {"property", "device"},
    ],
}


class CanonicalMultiHopReasoner:
    """Finds multi-hop reasoning paths through the canonical concept graph.

    Operates on deduplicated concept nodes, making cross-paper path
    discovery possible (the primary KG value proposition).
    """

    def __init__(
        self,
        graph,  # CanonicalGraph
        max_hops: int = 3,
        min_path_confidence: float = 0.15,
        prefer_cross_paper: bool = True,
    ):
        self.graph = graph
        self.max_hops = min(max_hops, 3)
        self.min_path_confidence = min_path_confidence
        self.prefer_cross_paper = prefer_cross_paper

    def find_paths(self, limit: int = 30) -> list[CanonicalReasoningPath]:
        """Find interesting reasoning paths across the canonical graph."""
        all_paths: list[CanonicalReasoningPath] = []

        for cname in self.graph.concepts:
            paths = self._bfs_from(cname)
            all_paths.extend(paths)
            if len(all_paths) >= limit * 5:
                break

        # Filter
        valid = [p for p in all_paths if p.path_confidence >= self.min_path_confidence]

        # Sort: cross-paper first, then template match, then confidence
        def _sort_key(p: CanonicalReasoningPath) -> tuple:
            return (
                -(1 if self.prefer_cross_paper and p.is_cross_paper else 0),
                -(1 if p.template_match else 0),
                -p.path_confidence,
            )

        valid.sort(key=_sort_key)

        # Deduplicate by concept set
        seen: set[frozenset[str]] = set()
        deduped: list[CanonicalReasoningPath] = []
        for p in valid:
            key = frozenset(p.concepts)
            if key not in seen:
                seen.add(key)
                deduped.append(p)

        return deduped[:limit]

    def _bfs_from(self, start: str) -> list[CanonicalReasoningPath]:
        """BFS from a concept, collecting paths of 2+ hops."""
        paths: list[CanonicalReasoningPath] = []
        # (current, concepts, relations, visited)
        queue: list[tuple[str, list[str], list[str], set[str]]] = [
            (start, [start], [], {start}),
        ]

        while queue:
            current, concepts, relations, visited = queue.pop(0)
            hop_count = len(relations)

            if hop_count >= 2:
                path = self._build_canonical_path(concepts, relations)
                if path.path_confidence >= self.min_path_confidence:
                    paths.append(path)

            if hop_count >= self.max_hops:
                continue

            for edge in self.graph.get_neighbors(current):
                target = edge.target_canonical
                if target not in visited and target in self.graph.concepts:
                    queue.append((
                        target,
                        concepts + [target],
                        relations + [edge.relation_type],
                        visited | {target},
                    ))

        return paths

    def _build_canonical_path(
        self, concepts: list[str], relations: list[str],
    ) -> CanonicalReasoningPath:
        """Build a CanonicalReasoningPath with confidence and metadata."""
        paper_ids: set[str] = set()
        confidences: list[float] = []

        for cname in concepts:
            concept = self.graph.concepts.get(cname)
            if concept:
                paper_ids.update(concept.source_paper_ids)
                confidences.append(concept.confidence)

        # Edge confidences from graph
        for i, rel_type in enumerate(relations):
            src = concepts[i]
            tgt = concepts[i + 1] if i + 1 < len(concepts) else None
            if src and tgt:
                for edge in self.graph.get_neighbors(src):
                    if edge.target_canonical == tgt and edge.relation_type == rel_type:
                        confidences.append(edge.confidence)
                        break

        # Geometric mean confidence
        if confidences:
            from functools import reduce
            import operator
            product = reduce(operator.mul, confidences, 1.0)
            geo_mean = product ** (1.0 / len(confidences))
        else:
            geo_mean = 0.0

        # Build trace
        trace_parts = []
        for i, rel in enumerate(relations):
            src = concepts[i]
            tgt = concepts[i + 1] if i + 1 < len(concepts) else "?"
            trace_parts.append(f"{src} {rel} {tgt}")
        trace = ", therefore ".join(trace_parts)

        # Template matching
        template_match = self._match_template(concepts)

        return CanonicalReasoningPath(
            concepts=list(concepts),
            relations=list(relations),
            hop_count=len(relations),
            path_confidence=round(geo_mean, 4),
            is_cross_paper=len(paper_ids) > 1,
            paper_ids=paper_ids,
            reasoning_trace=trace,
            template_match=template_match,
        )

    def _match_template(self, concepts: list[str]) -> str:
        """Check if the path matches a known scientific motif template."""
        types = []
        for cname in concepts:
            concept = self.graph.concepts.get(cname)
            if concept:
                types.append(concept.entity_type)
            else:
                types.append("")

        for template_name, type_slots in PATH_TEMPLATES.items():
            if len(types) != len(type_slots):
                continue
            match = all(
                types[i] in slot for i, slot in enumerate(type_slots)
            )
            if match:
                return template_name

        return ""

    def paths_to_evidence(self, paths: list[CanonicalReasoningPath]) -> list[EvidenceItem]:
        """Convert canonical paths to EvidenceItems."""
        return [p.to_evidence_item() for p in paths]
