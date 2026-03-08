"""Cross-domain synthesis engine for the Breakthrough Engine.

Phase 5 addition. Generates hybrid hypotheses that intentionally bridge
two domains, with proper evidence assembly, fit scoring, and novelty support.

Key principle: synthesis must be genuine, not superficial mashups.

Provides:
- SynthesisContext: per-run cross-domain pairing metadata
- SynthesisEngine: builds context, manages pair rotation
- SynthesisFitEvaluator: scores cross-domain quality
- build_synthesis_prompt_addendum: formats context into prompt instructions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cross-domain sub-domain bridge definitions
# ---------------------------------------------------------------------------

# Bridge sub-domains that connect clean-energy and materials
BRIDGE_SUB_DOMAINS: dict[tuple[str, str], list[str]] = {
    ("clean-energy", "materials"): [
        "electrocatalysts for energy conversion",
        "advanced membranes for fuel cells",
        "thermoelectric materials for waste heat",
        "photovoltaic absorber materials",
        "battery electrode materials",
        "hydrogen storage materials",
        "thermal insulation materials",
        "corrosion-resistant coatings for offshore energy",
        "superconducting materials for grid",
        "phase-change materials for thermal storage",
    ],
}

# Pairing weights: how likely each sub-domain pair is to be selected
# Higher weight = more unexplored potential
DEFAULT_PAIR_WEIGHTS: dict[str, float] = {
    "electrocatalysts for energy conversion": 1.0,
    "advanced membranes for fuel cells": 1.0,
    "thermoelectric materials for waste heat": 0.8,
    "photovoltaic absorber materials": 1.0,
    "battery electrode materials": 1.0,
    "hydrogen storage materials": 0.9,
    "thermal insulation materials": 0.7,
    "corrosion-resistant coatings for offshore energy": 0.7,
    "superconducting materials for grid": 0.6,
    "phase-change materials for thermal storage": 0.8,
}

# Sub-domain mapping: which primary/secondary sub-domains pair with each bridge
BRIDGE_TO_SUB_DOMAINS: dict[str, tuple[str, str]] = {
    "electrocatalysts for energy conversion": ("fuel cells and electrolyzers", "catalytic materials"),
    "advanced membranes for fuel cells": ("fuel cells and electrolyzers", "polymer nanocomposites"),
    "thermoelectric materials for waste heat": ("thermal energy storage", "quantum materials"),
    "photovoltaic absorber materials": ("solar photovoltaics", "two-dimensional materials"),
    "battery electrode materials": ("grid-scale energy storage", "high-entropy alloys"),
    "hydrogen storage materials": ("green hydrogen production", "metal-organic frameworks"),
    "thermal insulation materials": ("building energy efficiency", "additive manufacturing materials"),
    "corrosion-resistant coatings for offshore energy": ("offshore energy systems", "self-healing materials"),
    "superconducting materials for grid": ("wind energy systems", "quantum materials"),
    "phase-change materials for thermal storage": ("thermal energy storage", "biomaterials and hydrogels"),
}

# Bridge rotation interval (runs between advancing to next bridge)
BRIDGE_ROTATION_INTERVAL = 2


# ---------------------------------------------------------------------------
# SynthesisContext dataclass
# ---------------------------------------------------------------------------

@dataclass
class SynthesisContext:
    """Per-run cross-domain synthesis configuration.

    Passed to candidate generators to steer generation toward genuine
    cross-domain hypotheses. Persisted to bt_synthesis_context.
    """

    run_id: str
    primary_domain: str
    secondary_domain: str
    primary_sub_domain: str = ""
    secondary_sub_domain: str = ""
    bridge_mechanism: str = ""
    pairing_policy: str = "rotating_pair"  # "fixed_pair" | "rotating_pair" | "weighted_pair"
    excluded_cross_themes: list[str] = field(default_factory=list)
    focus_angles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "primary_domain": self.primary_domain,
            "secondary_domain": self.secondary_domain,
            "primary_sub_domain": self.primary_sub_domain,
            "secondary_sub_domain": self.secondary_sub_domain,
            "bridge_mechanism": self.bridge_mechanism,
            "pairing_policy": self.pairing_policy,
            "excluded_cross_themes": self.excluded_cross_themes,
            "focus_angles": self.focus_angles,
        }


# ---------------------------------------------------------------------------
# Synthesis prompt addendum
# ---------------------------------------------------------------------------

def build_synthesis_prompt_addendum(ctx: SynthesisContext) -> str:
    """Format a SynthesisContext into additional prompt instructions.

    Appended to the evidence block to steer cross-domain generation.
    """
    lines = []

    lines.append(f"CROSS-DOMAIN SYNTHESIS MODE")
    lines.append(f"  PRIMARY DOMAIN: {ctx.primary_domain}")
    lines.append(f"  SECONDARY DOMAIN: {ctx.secondary_domain}")

    if ctx.primary_sub_domain:
        lines.append(f"  PRIMARY SUB-DOMAIN: {ctx.primary_sub_domain}")
    if ctx.secondary_sub_domain:
        lines.append(f"  SECONDARY SUB-DOMAIN: {ctx.secondary_sub_domain}")

    if ctx.bridge_mechanism:
        lines.append(f"  TARGET BRIDGE: {ctx.bridge_mechanism}")
        lines.append(
            "  Each hypothesis MUST include a concrete bridge mechanism connecting "
            "the two domains. The bridge must explain WHY the combination is non-trivial "
            "and WHAT specific mechanism enables cross-domain benefit."
        )

    lines.append(
        "SYNTHESIS REQUIREMENTS:"
    )
    lines.append(
        "  1. Each hypothesis must draw on knowledge/techniques from BOTH domains"
    )
    lines.append(
        "  2. The combination must be non-obvious — explain why it hasn't been tried"
    )
    lines.append(
        "  3. Specify the bridging mechanism in detail (how domain A's insight applies to domain B)"
    )
    lines.append(
        "  4. The expected outcome must be testable with resources from either domain"
    )
    lines.append(
        "  5. Do NOT generate superficial mashups or buzzword combinations"
    )

    if ctx.focus_angles:
        angles = ", ".join(ctx.focus_angles)
        lines.append(f"PREFERRED BRIDGE ANGLES: {angles}")

    if ctx.excluded_cross_themes:
        themes = "; ".join(ctx.excluded_cross_themes[:10])
        lines.append(f"AVOID THESE PREVIOUSLY EXPLORED CROSS-DOMAIN THEMES: {themes}")
        lines.append(
            "  These cross-domain combinations have already been generated. "
            "Find novel bridges between the domains."
        )

    header = "\nCROSS-DOMAIN SYNTHESIS CONSTRAINTS (apply to all hypotheses):"
    return header + "\n" + "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# SynthesisEngine
# ---------------------------------------------------------------------------

class SynthesisEngine:
    """Builds cross-domain synthesis context and manages pair rotation.

    Usage:
        engine = SynthesisEngine(repo)
        ctx = engine.build_context(run_id, "clean-energy", "materials")
        addendum = build_synthesis_prompt_addendum(ctx)
    """

    def __init__(self, repo):
        self._repo = repo

    def build_context(
        self,
        run_id: str,
        primary_domain: str,
        secondary_domain: str,
        pairing_policy: str = "rotating_pair",
        bridge_override: str = "",
    ) -> SynthesisContext:
        """Build a SynthesisContext for a new cross-domain run."""
        # Determine bridge sub-domain
        bridge = bridge_override or self._get_next_bridge(
            primary_domain, secondary_domain, pairing_policy
        )

        # Map bridge to primary/secondary sub-domains
        primary_sub, secondary_sub = BRIDGE_TO_SUB_DOMAINS.get(
            bridge, ("", "")
        )

        # Extract excluded themes from prior cross-domain candidates
        excluded = self._extract_excluded_cross_themes(
            primary_domain, secondary_domain
        )

        # Focus angles for this bridge
        focus_angles = self._get_focus_angles(bridge)

        ctx = SynthesisContext(
            run_id=run_id,
            primary_domain=primary_domain,
            secondary_domain=secondary_domain,
            primary_sub_domain=primary_sub,
            secondary_sub_domain=secondary_sub,
            bridge_mechanism=bridge,
            pairing_policy=pairing_policy,
            excluded_cross_themes=excluded,
            focus_angles=focus_angles,
        )

        self._persist_context(ctx)
        return ctx

    def advance_bridge_rotation(
        self, primary_domain: str, secondary_domain: str
    ) -> None:
        """Advance bridge rotation after a run completes."""
        pair_key = self._pair_key(primary_domain, secondary_domain)
        bridges = self._get_bridges(primary_domain, secondary_domain)
        if not bridges:
            return

        state = self._repo.get_rotation_state(pair_key)
        if state is None:
            index = 0
            total = 1
        else:
            total = state.get("total_runs", 0) + 1
            if total % BRIDGE_ROTATION_INTERVAL == 0:
                index = (state.get("sub_domain_index", 0) + 1) % len(bridges)
            else:
                index = state.get("sub_domain_index", 0)

        bridge = bridges[index] if bridges else ""
        self._repo.save_rotation_state(pair_key, bridge, index, total)

    def is_cross_domain_program(self, program) -> bool:
        """Check if a research program is configured for cross-domain synthesis."""
        domain = getattr(program, "domain", "")
        return "cross" in domain.lower() or "+" in domain

    def parse_domain_pair(self, domain: str) -> tuple[str, str]:
        """Parse a cross-domain string like 'clean-energy+materials' into a pair."""
        if "+" in domain:
            parts = domain.split("+", 1)
            return parts[0].strip(), parts[1].strip()
        # Default pair
        return "clean-energy", "materials"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pair_key(primary: str, secondary: str) -> str:
        """Canonical key for a domain pair (sorted for consistency)."""
        return f"synthesis:{'+'.join(sorted([primary, secondary]))}"

    def _get_bridges(self, primary: str, secondary: str) -> list[str]:
        """Get bridge sub-domains for a domain pair."""
        # Try both orderings
        for key in [(primary, secondary), (secondary, primary)]:
            if key in BRIDGE_SUB_DOMAINS:
                return BRIDGE_SUB_DOMAINS[key]
        return []

    def _get_next_bridge(
        self, primary: str, secondary: str, policy: str
    ) -> str:
        """Determine next bridge from rotation state."""
        bridges = self._get_bridges(primary, secondary)
        if not bridges:
            return ""

        if policy == "fixed_pair":
            return bridges[0]

        pair_key = self._pair_key(primary, secondary)
        state = self._repo.get_rotation_state(pair_key)

        if state is None:
            return bridges[0]

        index = state.get("sub_domain_index", 0) % len(bridges)
        return bridges[index]

    def _extract_excluded_cross_themes(
        self, primary: str, secondary: str, limit: int = 10
    ) -> list[str]:
        """Extract themes from prior cross-domain candidates."""
        try:
            # Look for candidates in the cross-domain domain
            cross_domain = f"{primary}+{secondary}"
            rows = self._repo.db.execute(
                """SELECT title FROM bt_candidates
                   WHERE domain IN (?, ?, 'cross-domain')
                   AND (title LIKE '%+%' OR title LIKE '%cross%' OR title LIKE '%bridge%'
                        OR title LIKE '%hybrid%' OR title LIKE '%synthesis%')
                   ORDER BY created_at DESC LIMIT 30""",
                (cross_domain, f"{secondary}+{primary}"),
            ).fetchall()

            themes = []
            for row in rows:
                title = row["title"] if isinstance(row, dict) else row[0]
                if title and len(themes) < limit:
                    themes.append(title[:80])
            return themes
        except Exception as e:
            logger.debug("Could not extract cross-domain themes: %s", e)
            return []

    def _get_focus_angles(self, bridge: str) -> list[str]:
        """Get specific research angles for a bridge sub-domain."""
        focus_map: dict[str, list[str]] = {
            "electrocatalysts for energy conversion": [
                "non-precious metal catalysts",
                "single-atom catalysts for HER/OER",
                "bifunctional electrode design",
            ],
            "advanced membranes for fuel cells": [
                "proton conductivity enhancement",
                "mechanical durability under cycling",
                "anion exchange membrane chemistry",
            ],
            "thermoelectric materials for waste heat": [
                "nanostructured phonon scattering",
                "band convergence strategies",
                "flexible thermoelectric generators",
            ],
            "photovoltaic absorber materials": [
                "defect tolerance in novel absorbers",
                "bandgap tuning via alloying",
                "2D/3D perovskite heterostructures",
            ],
            "battery electrode materials": [
                "high-entropy oxide cathodes",
                "silicon-carbon anode composites",
                "solid-state electrolyte interfaces",
            ],
            "hydrogen storage materials": [
                "MOF-based hydrogen adsorption",
                "metal hydride kinetics",
                "ammonia cracking catalysts",
            ],
            "thermal insulation materials": [
                "aerogel composites for buildings",
                "vacuum insulation panels",
                "bio-based insulation materials",
            ],
            "corrosion-resistant coatings for offshore energy": [
                "self-healing anti-corrosion coatings",
                "biofouling-resistant surfaces",
                "cathodic protection materials",
            ],
            "superconducting materials for grid": [
                "high-Tc superconductor tape",
                "fault current limiters",
                "superconducting cable cooling",
            ],
            "phase-change materials for thermal storage": [
                "encapsulation for cycling stability",
                "composite PCMs with enhanced conductivity",
                "bio-based phase-change materials",
            ],
        }
        return focus_map.get(bridge, [])

    def _persist_context(self, ctx: SynthesisContext) -> None:
        """Save synthesis context to DB."""
        try:
            self._repo.save_synthesis_context(ctx.to_dict())
        except Exception as e:
            logger.warning("Could not persist synthesis context: %s", e)


# ---------------------------------------------------------------------------
# Synthesis Fit Evaluator
# ---------------------------------------------------------------------------

@dataclass
class SynthesisFitResult:
    """Structured cross-domain synthesis quality assessment."""
    candidate_id: str
    cross_domain_fit_score: float = 0.0
    bridge_mechanism_score: float = 0.0
    evidence_balance_score: float = 0.0
    superficial_mashup_flag: bool = False
    synthesis_reasons: list[str] = field(default_factory=list)
    passed: bool = True

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "cross_domain_fit_score": round(self.cross_domain_fit_score, 3),
            "bridge_mechanism_score": round(self.bridge_mechanism_score, 3),
            "evidence_balance_score": round(self.evidence_balance_score, 3),
            "superficial_mashup_flag": self.superficial_mashup_flag,
            "synthesis_reasons": self.synthesis_reasons,
            "passed": self.passed,
        }


class SynthesisFitEvaluator:
    """Evaluates whether a cross-domain candidate is genuinely hybrid.

    Scores:
    - bridge_mechanism_score: Does the mechanism reference both domains?
    - evidence_balance_score: Is evidence balanced across domains?
    - cross_domain_fit_score: Composite synthesis quality
    - superficial_mashup_flag: Penalizes weak combinations
    """

    def __init__(
        self,
        min_fit_score: float = 0.30,
        bridge_weight: float = 0.40,
        balance_weight: float = 0.30,
        depth_weight: float = 0.30,
    ):
        self.min_fit_score = min_fit_score
        self.bridge_weight = bridge_weight
        self.balance_weight = balance_weight
        self.depth_weight = depth_weight

    def evaluate(
        self,
        candidate,
        synthesis_ctx: SynthesisContext | None = None,
        evidence_roles: dict[str, str] | None = None,
    ) -> SynthesisFitResult:
        """Score synthesis quality for a cross-domain candidate."""
        result = SynthesisFitResult(candidate_id=candidate.id)

        if synthesis_ctx is None:
            # Not a synthesis run — auto-pass
            result.cross_domain_fit_score = 1.0
            result.passed = True
            result.synthesis_reasons.append("Not a synthesis run")
            return result

        primary = synthesis_ctx.primary_domain
        secondary = synthesis_ctx.secondary_domain

        # Bridge mechanism score: does the mechanism reference both domains?
        mech_text = (candidate.mechanism + " " + candidate.statement).lower()
        bridge_score = self._score_bridge_mechanism(
            mech_text, primary, secondary, synthesis_ctx.bridge_mechanism
        )
        result.bridge_mechanism_score = bridge_score

        # Evidence balance score
        balance_score = self._score_evidence_balance(evidence_roles or {})
        result.evidence_balance_score = balance_score

        # Depth score: length/detail of mechanism as proxy for non-superficiality
        depth_score = min(1.0, len(candidate.mechanism.strip()) / 200.0)

        # Composite
        result.cross_domain_fit_score = (
            bridge_score * self.bridge_weight
            + balance_score * self.balance_weight
            + depth_score * self.depth_weight
        )

        # Superficial mashup detection
        if bridge_score < 0.2:
            result.superficial_mashup_flag = True
            result.synthesis_reasons.append(
                "Weak bridge: mechanism does not reference both domains"
            )
        if balance_score < 0.1:
            result.superficial_mashup_flag = True
            result.synthesis_reasons.append(
                "Unbalanced evidence: dominated by one domain"
            )
        if depth_score < 0.3:
            result.synthesis_reasons.append(
                "Shallow mechanism: insufficient detail for cross-domain claim"
            )

        # Pass/fail
        if result.superficial_mashup_flag:
            result.cross_domain_fit_score *= 0.5  # penalty
            result.synthesis_reasons.append("Superficial mashup penalty applied")

        result.passed = result.cross_domain_fit_score >= self.min_fit_score

        if result.passed:
            result.synthesis_reasons.append(
                f"Synthesis quality: {result.cross_domain_fit_score:.2f} (pass)"
            )
        else:
            result.synthesis_reasons.append(
                f"Synthesis quality: {result.cross_domain_fit_score:.2f} < {self.min_fit_score} (fail)"
            )

        return result

    def _score_bridge_mechanism(
        self, text: str, primary: str, secondary: str, bridge: str
    ) -> float:
        """Score how well the mechanism bridges two domains."""
        score = 0.0

        # Check for domain-specific keywords
        primary_keywords = _domain_keywords(primary)
        secondary_keywords = _domain_keywords(secondary)

        primary_hits = sum(1 for kw in primary_keywords if kw in text)
        secondary_hits = sum(1 for kw in secondary_keywords if kw in text)

        if primary_hits > 0:
            score += 0.3
        if secondary_hits > 0:
            score += 0.3

        # Both domains referenced
        if primary_hits > 0 and secondary_hits > 0:
            score += 0.2

        # Bridge mechanism mentioned
        if bridge and any(word in text for word in bridge.lower().split()
                         if len(word) > 3):
            score += 0.2

        return min(1.0, score)

    @staticmethod
    def _score_evidence_balance(evidence_roles: dict[str, str]) -> float:
        """Score how balanced the evidence is across domains."""
        if not evidence_roles:
            return 0.5  # neutral if no role info

        role_counts = {"primary_support": 0, "secondary_support": 0, "bridge_support": 0}
        for role in evidence_roles.values():
            if role in role_counts:
                role_counts[role] += 1

        primary_count = role_counts["primary_support"]
        secondary_count = role_counts["secondary_support"]
        bridge_count = role_counts["bridge_support"]
        total = primary_count + secondary_count + bridge_count

        if total == 0:
            return 0.5

        # Perfect balance: equal primary and secondary
        if primary_count > 0 and secondary_count > 0:
            ratio = min(primary_count, secondary_count) / max(primary_count, secondary_count)
            balance = ratio * 0.7
        elif primary_count > 0 or secondary_count > 0:
            balance = 0.2  # one-sided
        else:
            balance = 0.1  # only bridge

        # Bridge evidence bonus
        if bridge_count > 0:
            balance += 0.3

        return min(1.0, balance)


# ---------------------------------------------------------------------------
# Evidence role tagging
# ---------------------------------------------------------------------------

def tag_evidence_roles(
    evidence_items: list,
    primary_domain: str,
    secondary_domain: str,
) -> dict[str, str]:
    """Tag evidence items by their role in cross-domain synthesis.

    Returns: {evidence_id: role} where role is one of:
    - primary_support
    - secondary_support
    - bridge_support
    """
    primary_kw = _domain_keywords(primary_domain)
    secondary_kw = _domain_keywords(secondary_domain)
    roles: dict[str, str] = {}

    for item in evidence_items:
        text = f"{item.title} {item.quote}".lower()
        primary_hits = sum(1 for kw in primary_kw if kw in text)
        secondary_hits = sum(1 for kw in secondary_kw if kw in text)

        if primary_hits > 0 and secondary_hits > 0:
            roles[item.id] = "bridge_support"
        elif primary_hits >= secondary_hits:
            roles[item.id] = "primary_support"
        else:
            roles[item.id] = "secondary_support"

    return roles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _domain_keywords(domain: str) -> list[str]:
    """Return identifying keywords for a domain."""
    keywords: dict[str, list[str]] = {
        "clean-energy": [
            "solar", "photovoltaic", "wind", "hydrogen", "electrolysis",
            "fuel cell", "battery", "grid", "renewable", "energy storage",
            "carbon capture", "thermoelectric", "heat pump", "thermal",
        ],
        "materials": [
            "alloy", "polymer", "ceramic", "composite", "nanomaterial",
            "graphene", "mof", "crystal", "superconductor", "metamaterial",
            "thin film", "coating", "catalyst", "membrane", "hydrogel",
        ],
    }
    return keywords.get(domain, [])
