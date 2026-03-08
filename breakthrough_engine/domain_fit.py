"""Domain-fit and program-relevance scoring for candidates.

Evaluates whether a candidate hypothesis is relevant to its assigned
research program domain. Produces structured domain_fit output used
in ranking/gating.

Phase 4B addition. Phase 4C: externalized config from YAML files.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .models import CandidateHypothesis, EvidenceItem, ResearchProgram

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain-fit config loading
# ---------------------------------------------------------------------------

@dataclass
class DomainFitConfig:
    """Loaded domain-fit configuration for a single domain."""
    domain: str
    positive_keywords: set[str] = field(default_factory=set)
    negative_keywords: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=lambda: {
        "title": 0.15, "statement": 0.30, "mechanism": 0.25,
        "evidence": 0.15, "keyword_diversity": 0.15,
    })
    min_score: float = 0.25
    program_goal_weight: float = 0.30
    off_domain_penalty: float = 0.15
    sub_domains: list[str] = field(default_factory=list)


def _config_dir() -> Path:
    repo_root = os.environ.get(
        "SCIRES_REPO_ROOT",
        str(Path(__file__).resolve().parent.parent),
    )
    return Path(repo_root) / "config" / "domain_fit"


_CONFIG_CACHE: dict[str, DomainFitConfig] = {}


def load_domain_fit_config(
    domain: str,
    config_dir: str | Path | None = None,
) -> DomainFitConfig:
    """Load domain-fit config from YAML. Falls back to built-in defaults."""
    if domain in _CONFIG_CACHE:
        return _CONFIG_CACHE[domain]

    d = Path(config_dir) if config_dir else _config_dir()

    # Try exact match, then partial match
    candidates = [
        d / f"{domain}.yaml",
        d / f"{domain.replace('-', '_')}.yaml",
        d / f"{domain.replace('_', '-')}.yaml",
    ]
    # Also try partial: materials-science -> materials
    if "-" in domain:
        candidates.append(d / f"{domain.split('-')[0]}.yaml")
    # Cross-domain: clean-energy+materials -> cross_domain.yaml
    if "+" in domain:
        candidates.insert(0, d / "cross_domain.yaml")

    for path in candidates:
        if path.exists():
            try:
                with open(path) as f:
                    data = yaml.safe_load(f) or {}
                config = DomainFitConfig(
                    domain=data.get("domain", domain),
                    positive_keywords=set(data.get("positive_keywords", [])),
                    negative_keywords=data.get("negative_keywords", []),
                    weights=data.get("weights") or {"title": 0.15, "statement": 0.30, "mechanism": 0.25, "evidence": 0.15, "keyword_diversity": 0.15},
                    min_score=data.get("min_score", 0.25),
                    program_goal_weight=data.get("program_goal_weight", 0.30),
                    off_domain_penalty=data.get("off_domain_penalty", 0.15),
                    sub_domains=data.get("sub_domains", []),
                )
                _CONFIG_CACHE[domain] = config
                logger.info("Loaded domain-fit config for '%s' from %s", domain, path)
                return config
            except Exception as e:
                logger.warning("Failed to load domain-fit config from %s: %s", path, e)

    # Fallback: empty config (cross-domain behavior)
    logger.info("No domain-fit config for '%s', using cross-domain defaults", domain)
    config = DomainFitConfig(domain=domain)
    _CONFIG_CACHE[domain] = config
    return config


def clear_config_cache() -> None:
    """Clear the config cache (for tests)."""
    _CONFIG_CACHE.clear()


def list_domain_configs(config_dir: str | Path | None = None) -> list[str]:
    """Return list of available domain config names."""
    d = Path(config_dir) if config_dir else _config_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


# ---------------------------------------------------------------------------
# Keyword matching helpers
# ---------------------------------------------------------------------------

def _keyword_hit_ratio(text: str, keywords: set[str]) -> tuple[float, list[str]]:
    """Return (ratio of keywords found in text, list of matched keywords)."""
    if not keywords:
        return 1.0, []  # cross-domain: always fits
    text_lower = text.lower()
    matched = [kw for kw in keywords if kw in text_lower]
    ratio = min(1.0, len(matched) / 3.0) if keywords else 1.0
    return ratio, matched


# ---------------------------------------------------------------------------
# Domain Fit Result
# ---------------------------------------------------------------------------

@dataclass
class DomainFitResult:
    """Structured domain-fit assessment for a candidate."""
    candidate_id: str
    domain: str
    domain_fit_score: float = 0.0
    title_relevance: float = 0.0
    statement_relevance: float = 0.0
    mechanism_relevance: float = 0.0
    evidence_relevance: float = 0.0
    relevance_reasons: list[str] = field(default_factory=list)
    mismatch_flags: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    passed: bool = True

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "domain": self.domain,
            "domain_fit_score": round(self.domain_fit_score, 3),
            "title_relevance": round(self.title_relevance, 3),
            "statement_relevance": round(self.statement_relevance, 3),
            "mechanism_relevance": round(self.mechanism_relevance, 3),
            "evidence_relevance": round(self.evidence_relevance, 3),
            "relevance_reasons": self.relevance_reasons,
            "mismatch_flags": self.mismatch_flags,
            "matched_keywords": self.matched_keywords,
            "passed": self.passed,
        }


# ---------------------------------------------------------------------------
# Domain Fit Evaluator
# ---------------------------------------------------------------------------

class DomainFitEvaluator:
    """Evaluates candidate domain relevance against the research program.

    Loads domain-fit configuration from YAML files in config/domain_fit/.
    Falls back to cross-domain (accept all) if no config is found.
    """

    def __init__(
        self,
        min_score: float | None = None,
        program_goal_weight: float | None = None,
        config_dir: str | Path | None = None,
    ):
        self._min_score_override = min_score
        self._goal_weight_override = program_goal_weight
        self._config_dir = config_dir

    def evaluate(
        self,
        candidate: CandidateHypothesis,
        program: ResearchProgram,
        evidence: list[EvidenceItem] | None = None,
    ) -> DomainFitResult:
        """Score domain fit of a candidate against its research program."""
        result = DomainFitResult(
            candidate_id=candidate.id,
            domain=program.domain,
        )

        config = load_domain_fit_config(program.domain, config_dir=self._config_dir)
        keywords = config.positive_keywords
        min_score = self._min_score_override if self._min_score_override is not None else config.min_score
        goal_weight = self._goal_weight_override if self._goal_weight_override is not None else config.program_goal_weight
        weights = config.weights

        # If cross-domain or no keywords defined, auto-pass
        if not keywords:
            result.domain_fit_score = 1.0
            result.title_relevance = 1.0
            result.statement_relevance = 1.0
            result.mechanism_relevance = 1.0
            result.evidence_relevance = 1.0
            result.relevance_reasons.append("Cross-domain program: all topics accepted")
            result.passed = True
            return result

        all_matched: list[str] = []

        # Title relevance
        t_ratio, t_matched = _keyword_hit_ratio(candidate.title, keywords)
        result.title_relevance = t_ratio
        all_matched.extend(t_matched)

        # Statement relevance
        s_ratio, s_matched = _keyword_hit_ratio(candidate.statement, keywords)
        result.statement_relevance = s_ratio
        all_matched.extend(s_matched)

        # Mechanism relevance
        m_ratio, m_matched = _keyword_hit_ratio(candidate.mechanism, keywords)
        result.mechanism_relevance = m_ratio
        all_matched.extend(m_matched)

        # Evidence relevance (average across evidence items)
        if evidence:
            ev_scores = []
            for ev in evidence:
                ev_text = f"{ev.title} {ev.quote}"
                ev_ratio, ev_matched = _keyword_hit_ratio(ev_text, keywords)
                ev_scores.append(ev_ratio)
                all_matched.extend(ev_matched)
            result.evidence_relevance = sum(ev_scores) / len(ev_scores) if ev_scores else 0.0
        else:
            result.evidence_relevance = 0.5  # neutral if no evidence

        # Program goal bonus: check candidate text against program goal
        goal_bonus = 0.0
        if program.goal:
            goal_ratio, goal_matched = _keyword_hit_ratio(
                candidate.statement + " " + candidate.mechanism,
                set(re.findall(r"[a-z]{4,}", program.goal.lower()))
            )
            goal_bonus = goal_ratio * goal_weight
            if goal_matched:
                result.relevance_reasons.append(
                    f"Matches program goal terms: {', '.join(goal_matched[:5])}"
                )

        # Composite score
        w = weights if isinstance(weights, dict) else DomainFitConfig().weights
        result.domain_fit_score = (
            result.title_relevance * w.get("title", 0.15)
            + result.statement_relevance * w.get("statement", 0.30)
            + result.mechanism_relevance * w.get("mechanism", 0.25)
            + result.evidence_relevance * w.get("evidence", 0.15)
            + goal_bonus
            + w.get("keyword_diversity", 0.15) * min(1.0, len(set(all_matched)) / 3.0)
        )
        result.domain_fit_score = min(1.0, result.domain_fit_score)

        result.matched_keywords = sorted(set(all_matched))

        # Generate reasons
        if result.matched_keywords:
            result.relevance_reasons.append(
                f"Domain keywords matched: {', '.join(result.matched_keywords[:8])}"
            )

        # Check for off-domain terms
        candidate_text = f"{candidate.title} {candidate.statement} {candidate.mechanism}".lower()
        for term in config.negative_keywords:
            if term in candidate_text:
                result.mismatch_flags.append(f"Off-domain term detected: '{term}'")
                result.domain_fit_score = max(0.0, result.domain_fit_score - config.off_domain_penalty)

        # Pass/fail
        result.passed = result.domain_fit_score >= min_score

        if not result.passed:
            result.mismatch_flags.append(
                f"Domain fit score {result.domain_fit_score:.2f} below threshold {min_score:.2f}"
            )
            logger.info(
                "Domain fit FAIL for '%s': score=%.2f, domain=%s",
                candidate.title[:40], result.domain_fit_score, program.domain,
            )

        return result
