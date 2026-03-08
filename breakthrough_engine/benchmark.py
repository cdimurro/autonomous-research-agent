"""Benchmark fixtures and regression harness for the Breakthrough Engine.

Golden cases covering key candidate quality scenarios:
- high-quality publishable candidate
- generic/unusable candidate
- duplicate candidate
- evidence-poor candidate
- overconfident claim
- simulation-unready candidate
- publishable finalist
- no-publication run (all rejected)

The regression harness runs the orchestrator in deterministic mode and
verifies output status, score ranges, publication behavior, and invariants.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .candidate_generator import CandidateGenerator, FakeCandidateGenerator
from .db import Repository, init_db
from .evidence_source import DemoFixtureSource, EvidenceSource
from .harnesses import run_publication_gate
from .models import (
    CandidateHypothesis,
    CandidateScore,
    CandidateStatus,
    EvidenceItem,
    EvidencePack,
    ResearchProgram,
    RunMode,
    RunRecord,
    RunStatus,
    new_id,
)
from .orchestrator import BreakthroughOrchestrator
from .scoring import rank_candidates, score_candidate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Golden case fixtures
# ---------------------------------------------------------------------------

def golden_high_quality() -> CandidateHypothesis:
    """A plausible, well-evidenced, publishable candidate."""
    return CandidateHypothesis(
        id="bench_high_quality",
        title="Perovskite-TI Hybrid Solar Cell",
        domain="clean_energy",
        statement="Combining methylammonium-free perovskite absorbers with Bi2Te3 topological insulator contacts will increase power conversion efficiency to >26% by reducing surface recombination through topological surface states.",
        mechanism="Topological surface states in Bi2Te3 provide spin-momentum locked charge transport channels at the perovskite-contact interface, suppressing surface recombination via spin-orbit coupling.",
        expected_outcome="Power conversion efficiency exceeding 26% in single-junction configuration, with reduced voltage deficit measurable via photoluminescence quantum yield.",
        testability_window_hours=48.0,
        novelty_notes="No prior work has combined topological insulator contacts with methylammonium-free perovskites. This bridges two independent breakthroughs in photovoltaics and condensed matter physics.",
        assumptions=["Bi2Te3 surface states survive perovskite deposition", "Lattice mismatch is manageable"],
        risk_flags=["Interface stability under illumination unknown"],
    )


def golden_generic() -> CandidateHypothesis:
    """A generic, unusable candidate that should fail hypothesis harness."""
    return CandidateHypothesis(
        id="bench_generic",
        title="General Improvement",
        domain="cross-domain",
        statement="This could potentially improve things significantly.",
        mechanism="",
        expected_outcome="Better results.",
        testability_window_hours=0.0,
        novelty_notes="",
        assumptions=[],
        risk_flags=[],
    )


def golden_duplicate(prior_statement: str) -> CandidateHypothesis:
    """A near-duplicate of a prior candidate."""
    return CandidateHypothesis(
        id="bench_duplicate",
        title="Perovskite-TI Solar Cell (duplicate)",
        domain="clean_energy",
        statement=prior_statement,  # Exact or near-exact copy
        mechanism="Same mechanism as previously published candidate.",
        expected_outcome="Same outcome as prior work.",
        testability_window_hours=48.0,
        novelty_notes="This is a duplicate of prior work.",
        assumptions=["Same assumptions"],
        risk_flags=[],
    )


def golden_evidence_poor() -> CandidateHypothesis:
    """A candidate with no evidence attachments."""
    return CandidateHypothesis(
        id="bench_evidence_poor",
        title="Unsupported Quantum Computing Breakthrough",
        domain="quantum",
        statement="A novel quantum error correction code using topological qubits will achieve fault tolerance at 10x lower overhead than surface codes by exploiting Fibonacci anyons.",
        mechanism="Fibonacci anyons in fractional quantum Hall states provide non-Abelian braiding statistics, enabling topologically protected quantum gates with inherent error correction.",
        expected_outcome="Demonstrated 10x reduction in qubit overhead for fault-tolerant quantum computation.",
        testability_window_hours=720.0,
        novelty_notes="Novel combination of Fibonacci anyons with practical error correction protocols.",
        assumptions=["Fibonacci anyons can be reliably created", "Braiding operations are fast enough"],
        risk_flags=["No experimental evidence for Fibonacci anyons at scale"],
        evidence_refs=[],  # No evidence
    )


def golden_overconfident() -> CandidateHypothesis:
    """A candidate making overconfident claims (should trigger warnings)."""
    return CandidateHypothesis(
        id="bench_overconfident",
        title="Room-Temperature Superconductor Discovery",
        domain="materials",
        statement="We have confirmed a room-temperature superconductor at ambient pressure using a novel hydrogen-rich compound. This is a proven discovery that will revolutionize energy transmission.",
        mechanism="High-frequency hydrogen vibrations in the LaH10 lattice create strong electron-phonon coupling sufficient for superconductivity at 300K and 1 atm.",
        expected_outcome="Zero resistance measured at 300K and ambient pressure in polycrystalline LaH10 samples.",
        testability_window_hours=24.0,
        novelty_notes="First room-temperature ambient-pressure superconductor.",
        assumptions=["LaH10 structure is stable at ambient pressure"],
        risk_flags=[],
    )


def golden_simulation_unready() -> CandidateHypothesis:
    """A candidate that should fail simulation harness (disallowed simulator)."""
    return CandidateHypothesis(
        id="bench_sim_unready",
        title="Dark Matter Detector Enhancement",
        domain="particle_physics",
        statement="Using a dual-phase xenon TPC with graphene-enhanced photodetectors will improve WIMP detection sensitivity by 100x through reduced dark noise.",
        mechanism="Graphene-based single-photon avalanche diodes replace conventional PMTs, reducing dark count rates by 3 orders of magnitude while maintaining >90% quantum efficiency at 175nm VUV scintillation wavelength.",
        expected_outcome="100x improvement in WIMP cross-section sensitivity in the 10-1000 GeV mass range.",
        testability_window_hours=8760.0,  # 1 year
        novelty_notes="Graphene SPADs have not been applied to noble liquid detectors.",
        assumptions=["Graphene SPADs function at liquid xenon temperature (-108C)"],
        risk_flags=["Extremely long validation timeline", "Requires major detector upgrade"],
    )


def golden_publishable_finalist() -> CandidateHypothesis:
    """A strong candidate that passes all gates but may not be the top pick."""
    return CandidateHypothesis(
        id="bench_finalist",
        title="MOF-Enhanced CRISPR Diagnostic",
        domain="diagnostics",
        statement="Integrating MOF-303 as a nucleic acid pre-concentration layer with CRISPR-Cas13 lateral flow assays will lower the detection limit to 1 copy/uL.",
        mechanism="MOF-303's 1200 m2/g surface area selectively adsorbs and concentrates target RNA. Released concentrated RNA is detected by CRISPR-Cas13 collateral cleavage reporter.",
        expected_outcome="10-fold improvement in detection limit validated on synthetic RNA standards.",
        testability_window_hours=24.0,
        novelty_notes="First application of MOFs as pre-concentration layers for CRISPR diagnostics.",
        assumptions=["MOF-303 does not inhibit Cas13 activity", "RNA desorption is efficient at RT"],
        risk_flags=["MOF batch variability"],
    )


# ---------------------------------------------------------------------------
# Benchmark generators
# ---------------------------------------------------------------------------

class BenchmarkCandidateGenerator(CandidateGenerator):
    """Generator that returns a specific set of golden-case candidates."""

    def __init__(self, candidates: list[CandidateHypothesis]):
        self._candidates = candidates

    def generate(
        self,
        evidence: list[EvidenceItem],
        domain: str,
        budget: int = 10,
        run_id: str = "",
    ) -> list[CandidateHypothesis]:
        result = []
        for c in self._candidates[:budget]:
            c.run_id = run_id
            c.domain = domain
            # Attach evidence refs if empty
            if not c.evidence_refs and evidence:
                c.evidence_refs = [e.id for e in evidence[:2]]
            result.append(c)
        return result


# ---------------------------------------------------------------------------
# Benchmark results
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkResult:
    """Result of a single benchmark case."""
    name: str
    passed: bool
    details: str = ""
    duration_ms: float = 0.0


@dataclass
class BenchmarkSuite:
    """Results of a full benchmark run."""
    results: list[BenchmarkResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    duration_ms: float = 0.0

    def add(self, result: BenchmarkResult):
        self.results.append(result)
        self.total += 1
        if result.passed:
            self.passed += 1
        else:
            self.failed += 1

    def summary(self) -> str:
        lines = [
            f"Benchmark Suite: {self.passed}/{self.total} passed, {self.failed} failed ({self.duration_ms:.0f}ms)",
            "",
        ]
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"  [{status}] {r.name} ({r.duration_ms:.0f}ms)")
            if not r.passed:
                lines.append(f"         {r.details}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Regression harness
# ---------------------------------------------------------------------------

def run_benchmark_suite() -> BenchmarkSuite:
    """Run the full benchmark suite and return results."""
    suite = BenchmarkSuite()
    start = time.time()

    suite.add(_bench_full_cycle_produces_publication())
    suite.add(_bench_one_publication_per_run())
    suite.add(_bench_generic_candidate_rejected())
    suite.add(_bench_evidence_poor_rejected())
    suite.add(_bench_overconfident_triggers_warning())
    suite.add(_bench_score_ranges_valid())
    suite.add(_bench_rejection_reasons_recorded())
    suite.add(_bench_high_threshold_no_publication())
    suite.add(_bench_deterministic_reproducibility())

    suite.duration_ms = (time.time() - start) * 1000
    return suite


def _make_deterministic_orchestrator(
    program: Optional[ResearchProgram] = None,
    generator: Optional[CandidateGenerator] = None,
) -> tuple[BreakthroughOrchestrator, Repository]:
    """Create a deterministic orchestrator with in-memory DB."""
    if program is None:
        program = ResearchProgram(
            name="benchmark",
            domain="clean_energy",
            mode=RunMode.DETERMINISTIC_TEST,
            candidate_budget=3,
            simulation_budget=3,
            publication_threshold=0.60,
        )

    db = init_db(in_memory=True)
    repo = Repository(db)

    orch = BreakthroughOrchestrator(
        program=program,
        repo=repo,
        evidence_source=DemoFixtureSource(),
        generator=generator or FakeCandidateGenerator(),
    )
    return orch, repo


def _bench_full_cycle_produces_publication() -> BenchmarkResult:
    """Standard cycle with good candidates should produce a publication."""
    start = time.time()
    try:
        orch, repo = _make_deterministic_orchestrator()
        run = orch.run()

        if run.status != RunStatus.COMPLETED:
            return BenchmarkResult("full_cycle_publication", False,
                                   f"Expected COMPLETED, got {run.status.value}",
                                   (time.time() - start) * 1000)
        if not run.publication_id:
            return BenchmarkResult("full_cycle_publication", False,
                                   "No publication produced",
                                   (time.time() - start) * 1000)

        pub = repo.get_publication(run.publication_id)
        if not pub:
            return BenchmarkResult("full_cycle_publication", False,
                                   "Publication not found in DB",
                                   (time.time() - start) * 1000)

        return BenchmarkResult("full_cycle_publication", True,
                               duration_ms=(time.time() - start) * 1000)
    except Exception as e:
        return BenchmarkResult("full_cycle_publication", False, str(e),
                               (time.time() - start) * 1000)


def _bench_one_publication_per_run() -> BenchmarkResult:
    """Invariant: at most one publication per run."""
    start = time.time()
    try:
        orch, repo = _make_deterministic_orchestrator()
        run = orch.run()

        pubs = repo.list_publications(limit=100)
        run_pubs = [p for p in pubs if p["run_id"] == run.id]

        if len(run_pubs) > 1:
            return BenchmarkResult("one_pub_per_run", False,
                                   f"Got {len(run_pubs)} publications for run",
                                   (time.time() - start) * 1000)
        return BenchmarkResult("one_pub_per_run", True,
                               duration_ms=(time.time() - start) * 1000)
    except Exception as e:
        return BenchmarkResult("one_pub_per_run", False, str(e),
                               (time.time() - start) * 1000)


def _bench_generic_candidate_rejected() -> BenchmarkResult:
    """A generic/empty candidate should be rejected by hypothesis harness."""
    start = time.time()
    try:
        gen = BenchmarkCandidateGenerator([golden_generic()])
        orch, repo = _make_deterministic_orchestrator(generator=gen)
        run = orch.run()

        if run.status != RunStatus.COMPLETED_NO_PUBLICATION:
            return BenchmarkResult("generic_rejected", False,
                                   f"Expected COMPLETED_NO_PUBLICATION, got {run.status.value}",
                                   (time.time() - start) * 1000)
        return BenchmarkResult("generic_rejected", True,
                               duration_ms=(time.time() - start) * 1000)
    except Exception as e:
        return BenchmarkResult("generic_rejected", False, str(e),
                               (time.time() - start) * 1000)


def _bench_evidence_poor_rejected() -> BenchmarkResult:
    """An evidence-poor candidate should be rejected."""
    start = time.time()
    try:
        gen = BenchmarkCandidateGenerator([golden_evidence_poor()])
        program = ResearchProgram(
            name="benchmark",
            domain="quantum",
            mode=RunMode.DETERMINISTIC_TEST,
            candidate_budget=1,
            simulation_budget=1,
            publication_threshold=0.60,
            evidence_minimum=3,  # Requires 3 evidence items
        )
        orch, repo = _make_deterministic_orchestrator(program=program, generator=gen)
        run = orch.run()

        rejections = repo.list_rejections(run.id)
        has_evidence_rejection = any(
            "evidence" in r.get("rejection_reason", "").lower()
            for r in rejections
        )

        # Either no publication or evidence harness rejected it
        if run.status == RunStatus.COMPLETED_NO_PUBLICATION or has_evidence_rejection:
            return BenchmarkResult("evidence_poor_rejected", True,
                                   duration_ms=(time.time() - start) * 1000)

        return BenchmarkResult("evidence_poor_rejected", False,
                               f"Expected rejection for evidence-poor candidate, status={run.status.value}",
                               (time.time() - start) * 1000)
    except Exception as e:
        return BenchmarkResult("evidence_poor_rejected", False, str(e),
                               (time.time() - start) * 1000)


def _bench_overconfident_triggers_warning() -> BenchmarkResult:
    """Overconfident claims should trigger harness warnings or failures."""
    start = time.time()
    try:
        from .harnesses import run_hypothesis_harness
        candidate = golden_overconfident()
        decision = run_hypothesis_harness(candidate, [])

        # Should have failed rules or warnings about claims
        has_issue = (
            not decision.passed
            or len(decision.warnings) > 0
            or len(decision.failed_rules) > 0
        )

        if has_issue:
            return BenchmarkResult("overconfident_warning", True,
                                   duration_ms=(time.time() - start) * 1000)
        return BenchmarkResult("overconfident_warning", False,
                               "Overconfident claim passed without warnings",
                               (time.time() - start) * 1000)
    except Exception as e:
        return BenchmarkResult("overconfident_warning", False, str(e),
                               (time.time() - start) * 1000)


def _bench_score_ranges_valid() -> BenchmarkResult:
    """All score dimensions should be in [0.0, 1.0]."""
    start = time.time()
    try:
        orch, repo = _make_deterministic_orchestrator()
        run = orch.run()

        candidates = repo.list_candidates_for_run(run.id)
        for c in candidates:
            score = repo.get_score(c["id"])
            if not score:
                continue
            for key in ["novelty_score", "plausibility_score", "impact_score",
                        "evidence_strength_score", "simulation_readiness_score",
                        "validation_cost_score", "final_score"]:
                val = score.get(key, 0)
                if not (0.0 <= val <= 1.0):
                    return BenchmarkResult("score_ranges", False,
                                           f"Score {key}={val} out of [0,1]",
                                           (time.time() - start) * 1000)

        return BenchmarkResult("score_ranges", True,
                               duration_ms=(time.time() - start) * 1000)
    except Exception as e:
        return BenchmarkResult("score_ranges", False, str(e),
                               (time.time() - start) * 1000)


def _bench_rejection_reasons_recorded() -> BenchmarkResult:
    """All rejected candidates should have recorded reasons."""
    start = time.time()
    try:
        orch, repo = _make_deterministic_orchestrator()
        run = orch.run()

        rejections = repo.list_rejections(run.id)
        for r in rejections:
            reason = r.get("rejection_reason", "")
            if not reason:
                return BenchmarkResult("rejection_reasons", False,
                                       f"Rejection for {r.get('candidate_id', '?')} has no reason",
                                       (time.time() - start) * 1000)

        return BenchmarkResult("rejection_reasons", True,
                               duration_ms=(time.time() - start) * 1000)
    except Exception as e:
        return BenchmarkResult("rejection_reasons", False, str(e),
                               (time.time() - start) * 1000)


def _bench_high_threshold_no_publication() -> BenchmarkResult:
    """With a very high publication threshold, no candidate should be published."""
    start = time.time()
    try:
        program = ResearchProgram(
            name="benchmark_high_threshold",
            domain="clean_energy",
            mode=RunMode.DETERMINISTIC_TEST,
            candidate_budget=3,
            simulation_budget=3,
            publication_threshold=0.99,  # Unreachable threshold
        )
        orch, repo = _make_deterministic_orchestrator(program=program)
        run = orch.run()

        if run.status != RunStatus.COMPLETED_NO_PUBLICATION:
            return BenchmarkResult("high_threshold_no_pub", False,
                                   f"Expected COMPLETED_NO_PUBLICATION, got {run.status.value}",
                                   (time.time() - start) * 1000)
        return BenchmarkResult("high_threshold_no_pub", True,
                               duration_ms=(time.time() - start) * 1000)
    except Exception as e:
        return BenchmarkResult("high_threshold_no_pub", False, str(e),
                               (time.time() - start) * 1000)


def _bench_deterministic_reproducibility() -> BenchmarkResult:
    """Two runs with same config should produce identical results."""
    start = time.time()
    try:
        orch1, repo1 = _make_deterministic_orchestrator()
        run1 = orch1.run()

        orch2, repo2 = _make_deterministic_orchestrator()
        run2 = orch2.run()

        # Compare statuses
        if run1.status != run2.status:
            return BenchmarkResult("deterministic", False,
                                   f"Statuses differ: {run1.status.value} vs {run2.status.value}",
                                   (time.time() - start) * 1000)

        # Compare publication existence
        if bool(run1.publication_id) != bool(run2.publication_id):
            return BenchmarkResult("deterministic", False,
                                   "Publication existence differs between runs",
                                   (time.time() - start) * 1000)

        return BenchmarkResult("deterministic", True,
                               duration_ms=(time.time() - start) * 1000)
    except Exception as e:
        return BenchmarkResult("deterministic", False, str(e),
                               (time.time() - start) * 1000)
