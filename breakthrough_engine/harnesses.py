"""Four deterministic harnesses / gates for the Breakthrough Engine.

Each harness takes structured input and returns a HarnessDecision.
No LLM calls. All logic is rule-based and deterministic.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from .models import (
    CandidateHypothesis,
    EvidencePack,
    HarnessDecision,
    SimulationSpec,
    CandidateScore,
    PublicationRecord,
    SimulationResult,
    SimulationStatus,
)


# ---------------------------------------------------------------------------
# 1. Hypothesis Legality Harness
# ---------------------------------------------------------------------------

def run_hypothesis_harness(
    candidate: CandidateHypothesis,
    prior_statements: list[str] | None = None,
) -> HarnessDecision:
    """Check specificity, testability, coherence, and duplication."""
    failed = []
    warnings = []
    fixes = []

    # Specificity: statement must be non-trivial
    if len(candidate.statement.strip()) < 20:
        failed.append("statement_too_short")
        fixes.append("Provide a more detailed hypothesis statement (>= 20 chars)")

    if not candidate.statement.strip():
        failed.append("empty_statement")

    # Must have mechanism
    if len(candidate.mechanism.strip()) < 10:
        failed.append("mechanism_missing_or_vague")
        fixes.append("Describe the causal mechanism in detail")

    # Must have expected outcome
    if len(candidate.expected_outcome.strip()) < 10:
        failed.append("expected_outcome_missing")
        fixes.append("Specify what measurable outcome is expected")

    # Testability window must be reasonable
    if candidate.testability_window_hours <= 0:
        failed.append("untestable_zero_window")
    elif candidate.testability_window_hours > 8760:  # > 1 year
        warnings.append("testability_window_very_long")

    # Must not be generic
    generic_phrases = [
        "further research is needed",
        "more study required",
        "it is possible that",
        "things could be better",
    ]
    lower_stmt = candidate.statement.lower()
    for phrase in generic_phrases:
        if phrase in lower_stmt:
            failed.append(f"generic_phrase_detected: {phrase}")
            fixes.append(f"Remove generic phrasing: '{phrase}'")

    # Overconfident or prohibited claims
    overconfident_phrases = [
        "confirmed discovery",
        "proven fact",
        "we have confirmed",
        "proven discovery",
        "will revolutionize",
        "is a proven",
    ]
    for phrase in overconfident_phrases:
        if phrase in lower_stmt:
            warnings.append(f"overconfident_claim: {phrase}")
            fixes.append(f"Remove overconfident language: '{phrase}'")

    # Must have at least one assumption disclosed
    if not candidate.assumptions:
        warnings.append("no_assumptions_disclosed")
        fixes.append("List at least one assumption")

    # Duplicate detection against prior candidates
    if prior_statements:
        for prior in prior_statements:
            similarity = SequenceMatcher(
                None, candidate.statement.lower(), prior.lower()
            ).ratio()
            if similarity > 0.85:
                failed.append("near_duplicate_of_prior_candidate")
                fixes.append("This hypothesis is too similar to a prior candidate")
                break

    passed = len(failed) == 0
    return HarnessDecision(
        harness_name="hypothesis_legality",
        candidate_id=candidate.id,
        passed=passed,
        failed_rules=failed,
        warnings=warnings,
        suggested_fixes=fixes,
        score_contribution=1.0 if passed else 0.0,
        explanation="Hypothesis legality check" + (
            ": PASSED" if passed else f": FAILED ({len(failed)} rules violated)"
        ),
    )


# ---------------------------------------------------------------------------
# 2. Evidence Legality Harness
# ---------------------------------------------------------------------------

def run_evidence_harness(
    pack: EvidencePack,
    minimum_evidence: int = 2,
) -> HarnessDecision:
    """Check evidence count, provenance, diversity, and language."""
    failed = []
    warnings = []
    fixes = []

    # Minimum evidence count
    if len(pack.items) < minimum_evidence:
        failed.append(f"insufficient_evidence_count ({len(pack.items)} < {minimum_evidence})")
        fixes.append(f"Provide at least {minimum_evidence} evidence items")

    # Each item must have quote and citation
    for i, item in enumerate(pack.items):
        if not item.quote.strip():
            failed.append(f"item_{i}_missing_quote")
            fixes.append(f"Evidence item {i} needs a verbatim quote")
        if not item.citation.strip():
            failed.append(f"item_{i}_missing_citation")
            fixes.append(f"Evidence item {i} needs a citation")

    # Source diversity
    unique_sources = len(set(item.source_id for item in pack.items))
    if unique_sources < 2 and len(pack.items) >= 2:
        warnings.append("low_source_diversity")
        fixes.append("Evidence should come from multiple independent sources")

    # Unsupported certainty language detection
    certainty_phrases = [
        "proves conclusively",
        "without doubt",
        "definitively establishes",
        "irrefutable evidence",
        "beyond any question",
    ]
    for item in pack.items:
        lower_quote = item.quote.lower()
        for phrase in certainty_phrases:
            if phrase in lower_quote:
                warnings.append(f"unsupported_certainty_language: '{phrase}'")

    passed = len(failed) == 0
    return HarnessDecision(
        harness_name="evidence_legality",
        candidate_id=pack.candidate_id,
        passed=passed,
        failed_rules=failed,
        warnings=warnings,
        suggested_fixes=fixes,
        score_contribution=1.0 if passed else 0.0,
        explanation="Evidence legality check" + (
            ": PASSED" if passed else f": FAILED ({len(failed)} rules violated)"
        ),
    )


# ---------------------------------------------------------------------------
# 3. Simulation Legality Harness
# ---------------------------------------------------------------------------

ALLOWED_SIMULATORS = {"mock", "omniverse"}

# Known parameter bounds for sanity checking
PARAMETER_BOUNDS = {
    "temperature_k": (0.0, 1e6),
    "pressure_pa": (0.0, 1e12),
    "time_seconds": (0.0, 1e10),
    "length_meters": (0.0, 1e12),
    "mass_kg": (0.0, 1e30),
    "velocity_ms": (0.0, 3e8),  # speed of light
    "energy_joules": (0.0, 1e45),
}


def run_simulation_harness(
    spec: SimulationSpec,
    runtime_budget_minutes: float = 60.0,
    allowed_simulators: list[str] | None = None,
) -> HarnessDecision:
    """Check simulator type, parameters, bounds, and runtime feasibility."""
    failed = []
    warnings = []
    fixes = []

    allowed = set(allowed_simulators) if allowed_simulators else ALLOWED_SIMULATORS

    # Simulator type
    if spec.simulator not in allowed:
        failed.append(f"simulator_not_allowed: {spec.simulator}")
        fixes.append(f"Use one of: {', '.join(sorted(allowed))}")

    # Runtime budget
    if spec.estimated_runtime_minutes > runtime_budget_minutes:
        failed.append(
            f"runtime_exceeds_budget ({spec.estimated_runtime_minutes:.1f} > {runtime_budget_minutes:.1f} min)"
        )
        fixes.append("Reduce simulation scope or increase budget")

    if spec.estimated_runtime_minutes <= 0:
        failed.append("invalid_runtime_estimate")

    # Parameter bounds checking
    for key, value in spec.parameters.items():
        if not isinstance(value, (int, float)):
            continue
        if key in PARAMETER_BOUNDS:
            lo, hi = PARAMETER_BOUNDS[key]
            if value < lo or value > hi:
                failed.append(
                    f"parameter_out_of_bounds: {key}={value} not in [{lo}, {hi}]"
                )
                fixes.append(f"Adjust {key} to be within physical bounds [{lo}, {hi}]")

    # Must have an objective
    if not spec.objective.strip():
        warnings.append("no_simulation_objective")
        fixes.append("Specify what the simulation should measure or test")

    # Impossible parameter combinations (extensible)
    temp = spec.parameters.get("temperature_k", None)
    if temp is not None and isinstance(temp, (int, float)) and temp < 0:
        failed.append("negative_absolute_temperature")

    passed = len(failed) == 0
    return HarnessDecision(
        harness_name="simulation_legality",
        candidate_id=spec.candidate_id,
        passed=passed,
        failed_rules=failed,
        warnings=warnings,
        suggested_fixes=fixes,
        score_contribution=1.0 if passed else 0.0,
        explanation="Simulation legality check" + (
            ": PASSED" if passed else f": FAILED ({len(failed)} rules violated)"
        ),
    )


# ---------------------------------------------------------------------------
# 4. Publication Gate Harness
# ---------------------------------------------------------------------------

def run_publication_gate(
    candidate: CandidateHypothesis,
    score: CandidateScore,
    evidence_pack: EvidencePack | None,
    simulation_result: SimulationResult | None,
    publication_threshold: float = 0.60,
) -> HarnessDecision:
    """Final gate before a candidate can be published.

    Phase 4B: Added evidence quality check, mechanism specificity check,
    and more explanatory diagnostics.
    """
    failed = []
    warnings = []
    fixes = []

    # Hypothesis must be explicit
    if len(candidate.statement.strip()) < 20:
        failed.append("hypothesis_not_explicit")

    # Evidence must be attached
    if evidence_pack is None or len(evidence_pack.items) == 0:
        failed.append("no_evidence_attached")
        fixes.append("Attach at least one evidence item")
    elif len(evidence_pack.items) < 2:
        warnings.append("weak_evidence_count")
        fixes.append("Attach at least 2 evidence items for stronger support")

    # Simulation result status
    if simulation_result is None:
        warnings.append("no_simulation_result")
    elif simulation_result.status == SimulationStatus.FAILED:
        failed.append("simulation_failed")
        fixes.append("Simulation must complete successfully or be marked skipped")

    # Assumptions must be disclosed
    if not candidate.assumptions:
        failed.append("assumptions_not_disclosed")
        fixes.append("Disclose at least one assumption")

    # Score above threshold
    if score.final_score < publication_threshold:
        failed.append(
            f"score_below_threshold ({score.final_score:.3f} < {publication_threshold:.3f})"
        )
        fixes.append("Improve candidate score above publication threshold")

    # Phase 4B: Evidence strength floor
    if score.evidence_strength_score < 0.3:
        warnings.append(f"low_evidence_strength ({score.evidence_strength_score:.2f})")
        fixes.append("Provide stronger, more relevant evidence")

    # Phase 4B: Mechanism specificity check
    if len(candidate.mechanism.strip()) < 50:
        warnings.append("mechanism_lacks_detail")
        fixes.append("Provide a more detailed mechanism description (>50 chars)")

    # Phase 4B: Novelty score floor
    if score.novelty_score < 0.3:
        warnings.append(f"low_novelty_score ({score.novelty_score:.2f})")

    # Must not claim confirmed discovery
    lower_stmt = candidate.statement.lower()
    if "confirmed discovery" in lower_stmt or "proven fact" in lower_stmt:
        failed.append("claims_confirmed_discovery")
        fixes.append("Label as 'validated_breakthrough_candidate', not confirmed discovery")

    passed = len(failed) == 0

    # Build explanatory diagnostic summary
    pass_reasons = []
    if passed:
        pass_reasons.append(f"score={score.final_score:.3f}>={publication_threshold:.3f}")
        pass_reasons.append(f"evidence={len(evidence_pack.items) if evidence_pack else 0}")
        pass_reasons.append(f"assumptions={len(candidate.assumptions)}")
        if warnings:
            pass_reasons.append(f"warnings={len(warnings)}")

    explanation = "Publication gate"
    if passed:
        explanation += f": PASSED ({'; '.join(pass_reasons)})"
    else:
        explanation += f": FAILED ({len(failed)} rules: {', '.join(failed[:3])})"

    return HarnessDecision(
        harness_name="publication_gate",
        candidate_id=candidate.id,
        passed=passed,
        failed_rules=failed,
        warnings=warnings,
        suggested_fixes=fixes,
        score_contribution=1.0 if passed else 0.0,
        explanation=explanation,
    )
