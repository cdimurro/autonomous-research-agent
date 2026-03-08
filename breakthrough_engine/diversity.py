"""Diversity-aware generation engine for the Breakthrough Engine.

Phase 4D addition. Solves novelty saturation by steering generation away from
already-explored semantic space. Works at the generation level, not matching level.

Key principle: never loosen novelty thresholds. Fix saturation at source.

Provides:
- DiversityContext: per-run steering parameters (sub-domain, excluded topics, focus areas)
- DiversityEngine: builds context from blocked candidates, manages sub-domain rotation
- build_diversity_prompt_addendum: formats context into prompt instructions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sub-domain definitions (loaded into domain_fit YAMLs but also available here)
# ---------------------------------------------------------------------------

# Default sub-domain lists per domain. These are overridden by the sub_domains
# field in domain_fit YAML configs when available.
DEFAULT_SUB_DOMAINS: dict[str, list[str]] = {
    "clean-energy": [
        "solar photovoltaics",
        "grid-scale energy storage",
        "green hydrogen production",
        "wind energy systems",
        "carbon capture and utilization",
        "thermal energy storage",
        "fuel cells and electrolyzers",
        "building energy efficiency",
        "offshore energy systems",
        "bioenergy and biomass",
    ],
    "materials": [
        "two-dimensional materials",
        "metal-organic frameworks",
        "high-entropy alloys",
        "biomaterials and hydrogels",
        "quantum materials",
        "polymer nanocomposites",
        "self-healing materials",
        "additive manufacturing materials",
        "catalytic materials",
        "optical and photonic materials",
    ],
    "cross-domain": [],
}

# Minimum run count before rotating to next sub-domain
SUB_DOMAIN_ROTATION_INTERVAL = 2


# ---------------------------------------------------------------------------
# DiversityContext dataclass
# ---------------------------------------------------------------------------


@dataclass
class DiversityContext:
    """Per-run diversity steering configuration.

    Passed to candidate generators to steer generation away from saturated
    semantic regions. Also persisted to bt_diversity_context for analysis.
    """

    run_id: str
    domain: str
    sub_domain: str = ""
    excluded_topics: list[str] = field(default_factory=list)
    excluded_neighbor_titles: list[str] = field(default_factory=list)
    rotation_policy: str = "auto"  # "auto" | "fixed" | "random"
    focus_areas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "domain": self.domain,
            "sub_domain": self.sub_domain,
            "excluded_topics": self.excluded_topics,
            "excluded_neighbor_titles": self.excluded_neighbor_titles,
            "rotation_policy": self.rotation_policy,
            "focus_areas": self.focus_areas,
        }


# ---------------------------------------------------------------------------
# Prompt addendum builder
# ---------------------------------------------------------------------------


def build_diversity_prompt_addendum(ctx: DiversityContext) -> str:
    """Format a DiversityContext into additional prompt instructions.

    This is appended to the evidence block before sending to the generator,
    steering the LLM away from saturated semantic regions.
    """
    lines = []

    if ctx.sub_domain:
        lines.append(f"SUB-DOMAIN FOCUS: {ctx.sub_domain}")
        lines.append(
            f"  All hypotheses must be specifically relevant to {ctx.sub_domain}. "
            "Do not generate broadly general hypotheses — zoom in on this area."
        )

    if ctx.focus_areas:
        areas = ", ".join(ctx.focus_areas)
        lines.append(f"PREFERRED FOCUS AREAS: {areas}")
        lines.append(
            "  Prioritize hypotheses that address these specific angles or gaps."
        )

    if ctx.excluded_topics:
        topics = "; ".join(ctx.excluded_topics[:10])  # cap to avoid prompt bloat
        lines.append(f"AVOID THESE OVER-EXPLORED TOPICS: {topics}")
        lines.append(
            "  These topics are saturated in our corpus. "
            "Generate hypotheses that approach the domain from different angles."
        )

    if ctx.excluded_neighbor_titles:
        titles = "; ".join(ctx.excluded_neighbor_titles[:8])
        lines.append(f"DO NOT REPRODUCE OR CLOSELY PARAPHRASE: {titles}")
        lines.append(
            "  These specific hypotheses already exist. "
            "Your output must be semantically distinct from them."
        )

    if not lines:
        return ""

    header = "\nDIVERSITY CONSTRAINTS (apply these to all hypotheses):"
    return header + "\n" + "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# DiversityEngine
# ---------------------------------------------------------------------------


class DiversityEngine:
    """Builds diversity context from blocked candidates and rotation state.

    Usage:
        engine = DiversityEngine(repo)
        ctx = engine.build_context(run_id, domain)
        # pass ctx to generator
        addendum = build_diversity_prompt_addendum(ctx)
    """

    def __init__(self, repo):
        """repo: Repository instance (or a duck-typed object with the same interface)."""
        self._repo = repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_context(
        self,
        run_id: str,
        domain: str,
        rotation_policy: str = "auto",
        sub_domain_override: str = "",
    ) -> DiversityContext:
        """Build a DiversityContext for a new run.

        Steps:
        1. Determine sub-domain via rotation (or override).
        2. Extract excluded topics from recent blocked candidates.
        3. Extract nearest-neighbor titles from embedding monitor.
        4. Return populated DiversityContext.
        """
        sub_domain = sub_domain_override or self._get_next_sub_domain(domain, rotation_policy)
        excluded_topics = self._extract_excluded_topics(domain)
        neighbor_titles = self._extract_neighbor_titles(domain)
        focus_areas = self._get_focus_areas(domain, sub_domain)

        ctx = DiversityContext(
            run_id=run_id,
            domain=domain,
            sub_domain=sub_domain,
            excluded_topics=excluded_topics,
            excluded_neighbor_titles=neighbor_titles,
            rotation_policy=rotation_policy,
            focus_areas=focus_areas,
        )

        self._persist_context(ctx)
        return ctx

    def advance_rotation(self, domain: str) -> None:
        """Call after a run completes to advance the sub-domain rotation index."""
        state = self._repo.get_rotation_state(domain)
        sub_domains = self._get_sub_domains(domain)
        if not sub_domains:
            return

        if state is None:
            index = 0
            total = 1
        else:
            total = state.get("total_runs", 0) + 1
            # Advance every SUB_DOMAIN_ROTATION_INTERVAL runs
            if total % SUB_DOMAIN_ROTATION_INTERVAL == 0:
                index = (state.get("sub_domain_index", 0) + 1) % len(sub_domains)
            else:
                index = state.get("sub_domain_index", 0)

        sub_domain = sub_domains[index] if sub_domains else ""
        self._repo.save_rotation_state(domain, sub_domain, index, total)
        logger.debug(
            "Rotation advanced: domain=%s sub_domain=%s index=%d total_runs=%d",
            domain, sub_domain, index, total,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_sub_domains(self, domain: str) -> list[str]:
        """Get sub-domain list for domain. Falls back to defaults."""
        try:
            from .domain_fit import load_domain_fit_config
            cfg = load_domain_fit_config(domain)
            if cfg and getattr(cfg, "sub_domains", None):
                return cfg.sub_domains
        except Exception:
            pass
        # Try default list with partial matching
        for key, subs in DEFAULT_SUB_DOMAINS.items():
            if domain.startswith(key) or key.startswith(domain.split("-")[0]):
                return subs
        return DEFAULT_SUB_DOMAINS.get(domain, [])

    def _get_next_sub_domain(self, domain: str, policy: str) -> str:
        """Determine next sub-domain from rotation state."""
        if policy == "fixed":
            return ""

        sub_domains = self._get_sub_domains(domain)
        if not sub_domains:
            return ""

        state = self._repo.get_rotation_state(domain)
        if state is None:
            return sub_domains[0]

        index = state.get("sub_domain_index", 0) % len(sub_domains)
        return sub_domains[index]

    def _extract_excluded_topics(self, domain: str, limit: int = 15) -> list[str]:
        """Extract over-represented topics from recent blocked candidates.

        Strategy: look at the titles of candidates that were blocked by the
        novelty gate (embedding similarity). Extract key noun phrases as topics
        to steer away from.
        """
        try:
            # Get recently blocked candidates for this domain
            rows = self._repo.db.execute(
                """SELECT title, statement FROM bt_candidates
                   WHERE domain=? AND status IN (
                       'novelty_failed', 'dedup_rejected',
                       'hypothesis_failed', 'evidence_failed',
                       'simulation_failed', 'publication_failed'
                   )
                   ORDER BY created_at DESC LIMIT 60""",
                (domain,),
            ).fetchall()

            if not rows:
                return []

            # Extract topic phrases from titles (simple noun phrase heuristic)
            topics = []
            seen: set[str] = set()
            for row in rows:
                phrases = _extract_title_topics(row["title"])
                for phrase in phrases:
                    if phrase not in seen and len(topics) < limit:
                        seen.add(phrase)
                        topics.append(phrase)

            return topics
        except Exception as e:
            logger.debug("Could not extract excluded topics: %s", e)
            return []

    def _extract_neighbor_titles(self, domain: str, limit: int = 8) -> list[str]:
        """Extract titles of candidates that appeared as nearest neighbors in embedding checks."""
        try:
            # Get recent embedding monitor records for this domain
            rows = self._repo.db.execute(
                """SELECT em.nearest_neighbor_summary
                   FROM bt_embedding_monitor em
                   JOIN bt_runs r ON em.run_id = r.id
                   WHERE r.domain=?
                   ORDER BY em.created_at DESC LIMIT 5""",
                (domain,),
            ).fetchall()

            if not rows:
                return []

            import json as _json
            titles: list[str] = []
            seen: set[str] = set()
            for row in rows:
                try:
                    neighbors = _json.loads(row["nearest_neighbor_summary"] or "[]")
                    for nb in neighbors:
                        title = nb.get("title", "")
                        if title and title not in seen and len(titles) < limit:
                            seen.add(title)
                            titles.append(title)
                except Exception:
                    continue
            return titles
        except Exception as e:
            logger.debug("Could not extract neighbor titles: %s", e)
            return []

    def _get_focus_areas(self, domain: str, sub_domain: str) -> list[str]:
        """Determine focus areas based on domain and sub-domain."""
        if not sub_domain:
            return []
        # Return 2-3 specific angles within the sub-domain
        focus_map: dict[str, list[str]] = {
            "solar photovoltaics": ["tandem cell architectures", "carrier recombination reduction", "stability under illumination"],
            "grid-scale energy storage": ["cycle life improvement", "fast charge/discharge kinetics", "safety under thermal stress"],
            "green hydrogen production": ["catalyst overpotential reduction", "membrane durability", "seawater electrolysis"],
            "wind energy systems": ["turbine blade materials", "offshore foundation design", "wake interaction reduction"],
            "carbon capture and utilization": ["sorbent regeneration energy", "direct air capture scaling", "CO2 utilization pathways"],
            "thermal energy storage": ["phase change material stability", "heat transfer enhancement", "long-duration storage"],
            "fuel cells and electrolyzers": ["membrane degradation", "platinum group metal reduction", "alkaline electrolysis"],
            "building energy efficiency": ["insulation materials", "passive cooling", "heat pump integration"],
            "two-dimensional materials": ["van der Waals heterostructures", "defect engineering", "scalable synthesis"],
            "metal-organic frameworks": ["pore size control", "water stability", "gas selectivity"],
            "high-entropy alloys": ["compositional optimization", "oxidation resistance", "processing routes"],
            "quantum materials": ["topological phase transitions", "superconducting gap engineering", "magnon transport"],
            "polymer nanocomposites": ["filler dispersion", "interfacial bonding", "mechanical-electrical property tradeoffs"],
            "catalytic materials": ["active site density", "selectivity control", "catalyst poisoning resistance"],
        }
        return focus_map.get(sub_domain, [])

    def _persist_context(self, ctx: DiversityContext) -> None:
        """Save context to bt_diversity_context table."""
        try:
            self._repo.save_diversity_context(ctx.to_dict())
        except Exception as e:
            logger.warning("Could not persist diversity context: %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_title_topics(title: str) -> list[str]:
    """Simple heuristic: extract multi-word noun phrases from title.

    Strips common words and returns the remaining content as topics.
    """
    STOP_WORDS = {
        "a", "an", "the", "and", "or", "for", "of", "in", "on", "with",
        "via", "by", "to", "from", "using", "based", "enhanced", "improved",
        "novel", "new", "efficient", "high", "low", "large", "small",
        "approach", "method", "system", "platform", "framework", "strategy",
    }

    words = title.lower().replace("-", " ").split()
    content_words = [w.strip(".,()[]") for w in words if w not in STOP_WORDS and len(w) > 3]

    # Build 2-gram phrases
    topics = []
    for i in range(len(content_words) - 1):
        phrase = f"{content_words[i]} {content_words[i+1]}"
        if len(phrase) > 6:
            topics.append(phrase)

    # Also include single long words as fallback
    if not topics:
        topics = [w for w in content_words if len(w) > 5]

    return topics[:3]  # max 3 topics per title
