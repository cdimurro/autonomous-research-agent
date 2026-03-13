"""Multi-signal segment relevance scoring.

Phase 10E: Replaces primitive single-anchor cosine similarity with a
composite score using multiple evidence-quality signals.

Signals:
1. Embedding similarity to domain anchor (preserved from Phase 10A)
2. Keyword overlap with domain terms
3. Quantitative result presence (numbers, units, percentages)
4. Evidence density (citation markers, reference patterns)
5. Mechanism specificity (causal/mechanistic language)

Each signal produces a [0,1] score. The composite is a weighted sum
with configurable, documented weights.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signal detectors
# ---------------------------------------------------------------------------

# Patterns for quantitative results
_QUANT_PATTERNS = [
    re.compile(r'\d+\.?\d*\s*%'),           # percentages
    re.compile(r'\d+\.?\d*\s*(nm|μm|mm|cm|m|kg|g|mg|μg|mL|L|mol|mmol|μmol)'),  # units
    re.compile(r'\d+\.?\d*\s*(eV|meV|keV|MeV|GeV|K|°C|GPa|MPa|kPa|W|kW|MW)'),  # physics
    re.compile(r'\d+\.?\d*\s*(mV|V|A|mA|Ω|Hz|kHz|MHz|GHz)'),  # electrical
    re.compile(r'\d+\.?\d*\s*[×x]\s*10\^?\d+'),  # scientific notation
    re.compile(r'(?:ZT|PCE|η|efficiency)\s*[=≈~]\s*\d'),  # named metrics
    re.compile(r'(?:increase|decrease|improve|reduce|enhance)\w*\s+(?:by|of)\s+\d'),  # change language
]

# Patterns for citation / evidence density
_CITATION_PATTERNS = [
    re.compile(r'\[\d+\]'),                  # [1], [2]
    re.compile(r'\((?:19|20)\d{2}\)'),       # (2024)
    re.compile(r'et\s+al\.'),                # et al.
    re.compile(r'(?:Fig|Table|Eq)\.\s*\d'),  # figure/table refs
    re.compile(r'doi:\s*10\.\d+'),           # DOI
]

# Causal / mechanistic language
_MECHANISM_KEYWORDS = frozenset({
    "causes", "inhibits", "enhances", "enables", "catalyzes",
    "mechanism", "pathway", "interaction", "binding", "electron",
    "phonon", "bandgap", "recombination", "transport", "diffusion",
    "absorption", "emission", "oxidation", "reduction", "synthesis",
    "decomposition", "crystallization", "doping", "interface",
    "coupling", "scattering", "tunneling", "excitation",
})

# Domain-specific keyword sets
DOMAIN_KEYWORDS: dict[str, frozenset[str]] = {
    "clean-energy": frozenset({
        "solar", "photovoltaic", "perovskite", "silicon", "tandem",
        "battery", "lithium", "solid-state", "electrolyte", "cathode",
        "anode", "hydrogen", "electrolysis", "fuel cell", "catalyst",
        "carbon capture", "mof", "dac", "co2", "sequestration",
        "thermoelectric", "thermophotovoltaic", "wind", "turbine",
        "efficiency", "power conversion", "energy density", "capacity",
        "renewable", "storage", "grid", "superconductor",
    }),
}


# ---------------------------------------------------------------------------
# Score components
# ---------------------------------------------------------------------------

@dataclass
class SegmentScoreBreakdown:
    """Per-segment score breakdown showing each signal's contribution."""
    segment_id: str = ""
    embedding_similarity: float = 0.0
    keyword_overlap: float = 0.0
    quantitative_density: float = 0.0
    citation_density: float = 0.0
    mechanism_specificity: float = 0.0
    composite_score: float = 0.0
    text_length: int = 0

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "embedding_similarity": round(self.embedding_similarity, 4),
            "keyword_overlap": round(self.keyword_overlap, 4),
            "quantitative_density": round(self.quantitative_density, 4),
            "citation_density": round(self.citation_density, 4),
            "mechanism_specificity": round(self.mechanism_specificity, 4),
            "composite_score": round(self.composite_score, 4),
            "text_length": self.text_length,
        }


@dataclass
class MultiSignalScoringConfig:
    """Configurable weights for multi-signal scoring."""
    embedding_weight: float = 0.30
    keyword_weight: float = 0.20
    quantitative_weight: float = 0.20
    citation_weight: float = 0.10
    mechanism_weight: float = 0.20
    domain: str = "clean-energy"

    def weights_dict(self) -> dict[str, float]:
        return {
            "embedding_similarity": self.embedding_weight,
            "keyword_overlap": self.keyword_weight,
            "quantitative_density": self.quantitative_weight,
            "citation_density": self.citation_weight,
            "mechanism_specificity": self.mechanism_weight,
        }


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def _keyword_overlap_score(text: str, domain: str) -> float:
    """Score keyword overlap between text and domain keyword set."""
    keywords = DOMAIN_KEYWORDS.get(domain, set())
    if not keywords:
        return 0.5  # neutral if no domain keywords defined

    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    # Saturates: 1 hit → ~0.15, 3 hits → ~0.45, 5+ hits → 0.75+
    return min(1.0, hits / max(1, len(keywords)) * 6.0)


def _quantitative_density_score(text: str) -> float:
    """Score presence and density of quantitative results."""
    hits = 0
    for pat in _QUANT_PATTERNS:
        hits += len(pat.findall(text))
    # Saturates: 1 match → 0.25, 3 → 0.60, 5+ → 0.85+
    return min(1.0, hits * 0.20)


def _citation_density_score(text: str) -> float:
    """Score citation and evidence reference density."""
    hits = 0
    for pat in _CITATION_PATTERNS:
        hits += len(pat.findall(text))
    return min(1.0, hits * 0.25)


def _mechanism_specificity_score(text: str) -> float:
    """Score presence of mechanistic/causal scientific language."""
    text_lower = text.lower()
    words = set(re.findall(r'\b\w+\b', text_lower))
    hits = len(words & _MECHANISM_KEYWORDS)
    # Saturates: 2 mechanism words → 0.30, 4 → 0.60, 6+ → 0.90
    return min(1.0, hits * 0.15)


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

class MultiSignalSegmentScorer:
    """Scores segments using multiple quality signals.

    Can operate with or without an embedding provider. When no
    embedding provider is available, the embedding_similarity signal
    defaults to 0.5 and other signals compensate.
    """

    def __init__(
        self,
        config: Optional[MultiSignalScoringConfig] = None,
        embedding_scorer=None,  # Optional SegmentRelevanceScorer from paper_ingestion
    ):
        self.config = config or MultiSignalScoringConfig()
        self._embedding_scorer = embedding_scorer

    def score(self, text: str, domain: str = "", segment_id: str = "") -> SegmentScoreBreakdown:
        """Score a single segment text using all signals."""
        domain = domain or self.config.domain
        breakdown = SegmentScoreBreakdown(
            segment_id=segment_id,
            text_length=len(text),
        )

        # Signal 1: Embedding similarity
        if self._embedding_scorer:
            breakdown.embedding_similarity = self._embedding_scorer.score(text, domain)
        else:
            breakdown.embedding_similarity = 0.5  # neutral default

        # Signal 2: Keyword overlap
        breakdown.keyword_overlap = _keyword_overlap_score(text, domain)

        # Signal 3: Quantitative density
        breakdown.quantitative_density = _quantitative_density_score(text)

        # Signal 4: Citation density
        breakdown.citation_density = _citation_density_score(text)

        # Signal 5: Mechanism specificity
        breakdown.mechanism_specificity = _mechanism_specificity_score(text)

        # Composite
        w = self.config.weights_dict()
        breakdown.composite_score = (
            breakdown.embedding_similarity * w["embedding_similarity"]
            + breakdown.keyword_overlap * w["keyword_overlap"]
            + breakdown.quantitative_density * w["quantitative_density"]
            + breakdown.citation_density * w["citation_density"]
            + breakdown.mechanism_specificity * w["mechanism_specificity"]
        )
        # Clamp to [0, 1]
        breakdown.composite_score = max(0.0, min(1.0, breakdown.composite_score))

        return breakdown

    def score_batch(
        self, texts: list[str], domain: str = "", segment_ids: list[str] | None = None,
    ) -> list[SegmentScoreBreakdown]:
        """Score multiple segments."""
        ids = segment_ids or [""] * len(texts)
        return [self.score(t, domain, sid) for t, sid in zip(texts, ids)]
