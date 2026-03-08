"""Daily cycle orchestrator for the Breakthrough Engine.

Runs the full pipeline from evidence gathering through publication.
Produces one published candidate per run and archives all others.

Phase 3 additions:
- Novelty gate between evidence and scoring
- Review workflow for production_review mode
- Shadow mode (no publication/draft)
- Metrics collection
- Notification hooks
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from .candidate_generator import (
    CandidateGenerator,
    DemoCandidateGenerator,
    FakeCandidateGenerator,
    OllamaCandidateGenerator,
)
from .db import Repository, init_db
from .evidence_source import DemoFixtureSource, ExistingFindingsSource, EvidenceSource
from .harnesses import (
    run_evidence_harness,
    run_hypothesis_harness,
    run_publication_gate,
    run_simulation_harness,
)
from .memory import RunMemory
from .models import (
    CandidateHypothesis,
    CandidateScore,
    CandidateStatus,
    EvidencePack,
    NoveltyDecision,
    PublicationRecord,
    ResearchProgram,
    RunMetrics,
    RunMode,
    RunRecord,
    RunStatus,
    SimulationSpec,
    SimulationResult,
    new_id,
)
from .notifications import NotificationDispatcher
from .corpus_manager import CorpusManager
from .diversity import DiversityEngine
from .domain_fit import DomainFitEvaluator
from .embedding_monitor import EmbeddingMonitor
from .embeddings import EmbeddingNoveltyEngine, MockEmbeddingProvider, EmbeddingProvider
from .novelty import NoveltyEngine
from .retrieval import rank_evidence
from .review import create_draft
from .scoring import rank_candidates, score_candidate
from .simulator import MockSimulatorAdapter, SimulatorAdapter, get_simulator

logger = logging.getLogger(__name__)

# Modes that auto-publish (no review gate)
AUTO_PUBLISH_MODES = {
    RunMode.DETERMINISTIC_TEST,
    RunMode.DEMO_LOCAL,
    RunMode.PRODUCTION_LOCAL,
    RunMode.OMNIVERSE_STUB,
    RunMode.OMNIVERSE_DRY_RUN,
}

# Modes that create drafts instead of auto-publishing
REVIEW_MODES = {RunMode.PRODUCTION_REVIEW}

# Modes that produce no publication or draft
SHADOW_MODES = {RunMode.PRODUCTION_SHADOW}


class BreakthroughOrchestrator:
    """Runs a single breakthrough discovery cycle.

    Each run:
    1. Gathers evidence
    2. Generates candidates
    3. Runs harness gates
    4. Evaluates novelty
    5. Scores and ranks
    6. Simulates top candidates
    7. Publishes, creates draft, or shadows (depending on mode)
    """

    def __init__(
        self,
        program: ResearchProgram,
        repo: Repository,
        evidence_source: Optional[EvidenceSource] = None,
        generator: Optional[CandidateGenerator] = None,
        simulator: Optional[SimulatorAdapter] = None,
        dispatcher: Optional[NotificationDispatcher] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ):
        self.program = program
        self.repo = repo
        self.memory = RunMemory(repo.db)
        self.novelty_engine = NoveltyEngine(repo.db)
        self.domain_fit_evaluator = DomainFitEvaluator()
        self.dispatcher = dispatcher or NotificationDispatcher()

        # Phase 4B: Embedding novelty engine
        emb_provider = embedding_provider or MockEmbeddingProvider()
        self.embedding_novelty = EmbeddingNoveltyEngine(provider=emb_provider)
        self.embedding_monitor = EmbeddingMonitor(repo)

        # Phase 4D: Diversity and corpus management
        self.diversity_engine = DiversityEngine(repo)
        self.corpus_manager = CorpusManager(repo)

        # Wire up components based on run mode
        if evidence_source:
            self.evidence_source = evidence_source
        elif program.mode in (RunMode.PRODUCTION_LOCAL, RunMode.PRODUCTION_REVIEW, RunMode.PRODUCTION_SHADOW):
            self.evidence_source = ExistingFindingsSource(repo.db)
        else:
            self.evidence_source = DemoFixtureSource()

        if generator:
            self.generator = generator
        elif program.mode == RunMode.DETERMINISTIC_TEST:
            self.generator = FakeCandidateGenerator()
        elif program.mode in (RunMode.PRODUCTION_LOCAL, RunMode.PRODUCTION_REVIEW,
                              RunMode.PRODUCTION_SHADOW, RunMode.OMNIVERSE_DRY_RUN):
            self.generator = OllamaCandidateGenerator()
        else:
            self.generator = DemoCandidateGenerator()

        if simulator:
            self.simulator = simulator
        elif program.mode in (RunMode.DETERMINISTIC_TEST, RunMode.DEMO_LOCAL,
                              RunMode.PRODUCTION_LOCAL, RunMode.PRODUCTION_REVIEW,
                              RunMode.PRODUCTION_SHADOW):
            self.simulator = MockSimulatorAdapter()
        elif program.mode == RunMode.OMNIVERSE_DRY_RUN:
            from .simulator import OmniverseSimulatorAdapter
            self.simulator = OmniverseSimulatorAdapter(dry_run=True)
        else:
            self.simulator = get_simulator(program.allowed_simulators[0])

    def run(self) -> RunRecord:
        """Execute a full breakthrough cycle. Returns the run record."""
        run = RunRecord(
            id=new_id(),
            program_name=self.program.name,
            mode=self.program.mode,
            status=RunStatus.STARTED,
        )
        self.repo.save_run(run)
        logger.info("Starting breakthrough run %s for program '%s' (mode=%s)",
                     run.id, self.program.name, self.program.mode.value)

        try:
            result = self._execute_cycle(run)
            return result
        except Exception as e:
            run.status = RunStatus.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self.repo.save_run(run)
            logger.error("Run %s failed: %s", run.id, e)
            self.dispatcher.run_failed(run.id, self.program.name, str(e))
            raise

    def _execute_cycle(self, run: RunRecord) -> RunRecord:
        metrics = RunMetrics(run_id=run.id)
        t0 = time.time()
        novelty_results: dict[str, object] = {}

        # Step 1: Gather evidence
        t_step = time.time()
        logger.info("[%s] Step 1: Gathering evidence", run.id[:8])
        evidence = self.evidence_source.gather(
            domain=self.program.domain, limit=20
        )
        metrics.evidence_count = len(evidence)
        metrics.stage_durations["evidence_gathering"] = round(time.time() - t_step, 2)
        logger.info("[%s] Gathered %d evidence items", run.id[:8], len(evidence))

        # Step 1.5: Pre-run corpus maintenance (Phase 4D)
        archival_stats: dict = {}
        try:
            archival_stats = self.corpus_manager.run_archival(self.program.domain)
            logger.info(
                "[%s] Corpus maintenance: archived_by_age=%d total_archived=%d active_size=%d",
                run.id[:8],
                archival_stats.get("archived_by_age", 0),
                archival_stats.get("total_archived", 0),
                self.corpus_manager.get_active_count(self.program.domain),
            )
        except Exception as e:
            logger.warning("[%s] Corpus archival failed (non-fatal): %s", run.id[:8], e)

        # Step 2: Generate candidates (with diversity steering)
        t_step = time.time()
        logger.info("[%s] Step 2: Generating candidates (budget=%d)", run.id[:8], self.program.candidate_budget)

        # Build diversity context for this run (Phase 4D)
        diversity_ctx = None
        try:
            diversity_ctx = self.diversity_engine.build_context(
                run_id=run.id,
                domain=self.program.domain,
            )
            logger.info(
                "[%s] Diversity context: sub_domain=%r excluded_topics=%d",
                run.id[:8],
                diversity_ctx.sub_domain,
                len(diversity_ctx.excluded_topics),
            )
        except Exception as e:
            logger.warning("[%s] Diversity context build failed (non-fatal): %s", run.id[:8], e)

        candidates = self.generator.generate(
            evidence=evidence,
            domain=self.program.domain,
            budget=self.program.candidate_budget,
            run_id=run.id,
            diversity_context=diversity_ctx,
        )
        run.candidates_generated = len(candidates)
        for c in candidates:
            c.run_id = run.id
            self.repo.save_candidate(c)
        metrics.stage_durations["candidate_generation"] = round(time.time() - t_step, 2)
        logger.info("[%s] Generated %d candidates", run.id[:8], len(candidates))

        # Step 3: Deduplicate
        t_step = time.time()
        logger.info("[%s] Step 3: Deduplication", run.id[:8])
        candidates = self._deduplicate(run, candidates)
        metrics.stage_durations["deduplication"] = round(time.time() - t_step, 2)

        # Step 4: Hypothesis harness
        t_step = time.time()
        logger.info("[%s] Step 4: Hypothesis legality harness", run.id[:8])
        candidates = self._run_hypothesis_gate(run, candidates)
        metrics.stage_durations["hypothesis_harness"] = round(time.time() - t_step, 2)

        # Step 5: Evidence packs + evidence harness
        t_step = time.time()
        logger.info("[%s] Step 5: Evidence assembly + legality harness", run.id[:8])
        evidence_packs: dict[str, EvidencePack] = {}
        candidates = self._run_evidence_gate(run, candidates, evidence, evidence_packs)
        metrics.stage_durations["evidence_harness"] = round(time.time() - t_step, 2)

        # Step 5.5: Novelty gate (Phase 3) + embedding novelty (Phase 4B)
        t_step = time.time()
        logger.info("[%s] Step 5.5: Novelty gate (lexical + embedding)", run.id[:8])
        # Phase 4C: Start embedding monitoring for this run
        self.embedding_monitor.start_run(
            run.id, self.embedding_novelty.provider,
            self.embedding_novelty.similarity_threshold,
            self.embedding_novelty.warn_threshold,
        )
        candidates = self._run_novelty_gate(run, candidates, evidence, novelty_results)
        metrics.novelty_fail_count = sum(
            1 for nr in novelty_results.values()
            if hasattr(nr, 'decision') and nr.decision == NoveltyDecision.FAIL
        )
        metrics.novelty_warn_count = sum(
            1 for nr in novelty_results.values()
            if hasattr(nr, 'decision') and nr.decision == NoveltyDecision.WARN
        )
        metrics.stage_durations["novelty_gate"] = round(time.time() - t_step, 2)

        # Step 5.6: Domain-fit gate (Phase 4B)
        t_step = time.time()
        logger.info("[%s] Step 5.6: Domain-fit gate", run.id[:8])
        domain_fit_results: dict[str, object] = {}
        candidates = self._run_domain_fit_gate(run, candidates, evidence, domain_fit_results)
        metrics.stage_durations["domain_fit_gate"] = round(time.time() - t_step, 2)

        # Step 6: Score and rank
        t_step = time.time()
        logger.info("[%s] Step 6: Scoring and ranking", run.id[:8])
        scores: dict[str, CandidateScore] = {}
        harness_decisions_map: dict[str, list] = {}
        for c in candidates:
            decisions = self.repo.get_harness_decisions(c.id)
            from .models import HarnessDecision as HD
            hd_list = [HD(
                harness_name=d["harness_name"],
                candidate_id=d["candidate_id"],
                passed=bool(d["passed"]),
            ) for d in decisions]
            harness_decisions_map[c.id] = hd_list

            s = score_candidate(
                candidate=c,
                evidence_pack=evidence_packs.get(c.id),
                simulation_result=None,
                harness_decisions=hd_list,
                program=self.program,
            )
            scores[c.id] = s
            self.repo.save_score(s)

        # Select top K for simulation
        top_k = min(self.program.simulation_budget, len(candidates))
        ranked = rank_candidates(list(scores.values()))
        sim_candidates = [c for c in candidates if c.id in {r.candidate_id for r in ranked[:top_k]}]
        metrics.stage_durations["scoring"] = round(time.time() - t_step, 2)

        # Step 7: Build simulation specs + simulation harness
        t_step = time.time()
        logger.info("[%s] Step 7: Simulation specs + harness (top %d)", run.id[:8], top_k)
        sim_results: dict[str, SimulationResult] = {}
        sim_candidates = self._run_simulation_gate(
            run, sim_candidates, evidence_packs, sim_results
        )
        metrics.simulation_pass_count = len(sim_candidates)
        metrics.simulation_fail_count = top_k - len(sim_candidates)
        metrics.stage_durations["simulation"] = round(time.time() - t_step, 2)

        # Step 8: Re-score with simulation results
        t_step = time.time()
        logger.info("[%s] Step 8: Re-scoring with simulation results", run.id[:8])
        for c in sim_candidates:
            s = score_candidate(
                candidate=c,
                evidence_pack=evidence_packs.get(c.id),
                simulation_result=sim_results.get(c.id),
                harness_decisions=harness_decisions_map.get(c.id, []),
                program=self.program,
            )
            scores[c.id] = s
            self.repo.save_score(s)
        metrics.stage_durations["rescoring"] = round(time.time() - t_step, 2)

        # Step 9: Publication gate
        t_step = time.time()
        logger.info("[%s] Step 9: Publication gate", run.id[:8])
        publication_passed: dict[str, bool] = {}
        final_candidates = []
        for c in sim_candidates:
            decision = run_publication_gate(
                candidate=c,
                score=scores[c.id],
                evidence_pack=evidence_packs.get(c.id),
                simulation_result=sim_results.get(c.id),
                publication_threshold=self.program.publication_threshold,
            )
            self.repo.save_harness_decision(decision)
            publication_passed[c.id] = decision.passed

            # Phase 4B: Save publication gate diagnostic
            try:
                gate_reasons = []
                if decision.passed:
                    gate_reasons.append(f"score={scores[c.id].final_score:.3f} >= {self.program.publication_threshold}")
                    if decision.warnings:
                        gate_reasons.append(f"warnings: {', '.join(decision.warnings[:3])}")
                else:
                    gate_reasons.extend(decision.failed_rules)
                self.repo.save_gate_diagnostic(
                    run_id=run.id, candidate_id=c.id, gate_name="publication",
                    passed=decision.passed, score=scores[c.id].final_score,
                    reasons=gate_reasons,
                )
            except Exception:
                pass

            if decision.passed:
                final_candidates.append(c)
            else:
                self._reject(run, c, CandidateStatus.PUBLICATION_FAILED,
                             f"Publication gate failed: {', '.join(decision.failed_rules)}",
                             "publication_gate", decision.failed_rules)
        metrics.stage_durations["publication_gate"] = round(time.time() - t_step, 2)

        # Step 10: Select best and publish/draft/shadow
        t_step = time.time()
        logger.info("[%s] Step 10: Publication selection (mode=%s)", run.id[:8], self.program.mode.value)

        if self.program.mode in SHADOW_MODES:
            # Shadow mode: no publication or draft, but mark passing candidates as finalists
            if final_candidates:
                run.status = RunStatus.COMPLETED
                for c in final_candidates:
                    c.status = CandidateStatus.FINALIST
                    self.repo.update_candidate_status(c.id, CandidateStatus.FINALIST)
                logger.info("[%s] Shadow mode — %d finalist(s), no publication created",
                            run.id[:8], len(final_candidates))
            else:
                run.status = RunStatus.COMPLETED_NO_PUBLICATION
                logger.info("[%s] Shadow mode — no candidates passed publication gate", run.id[:8])
        elif final_candidates:
            final_ranked = rank_candidates(
                [scores[c.id] for c in final_candidates],
                publication_passed,
            )
            best_id = final_ranked[0].candidate_id
            best = next(c for c in final_candidates if c.id == best_id)

            if self.program.mode in REVIEW_MODES:
                # Create draft for review
                draft = create_draft(
                    repo=self.repo,
                    run_id=run.id,
                    candidate=best,
                    score=scores[best.id],
                    evidence_pack=evidence_packs.get(best.id),
                    simulation_result=sim_results.get(best.id),
                    novelty_result=novelty_results.get(best.id),
                )
                run.status = RunStatus.COMPLETED
                metrics.draft_created = True
                logger.info("[%s] Draft created: %s (score=%.3f)",
                            run.id[:8], best.title, scores[best.id].final_score)

                # Mark remaining as finalists
                for c in final_candidates:
                    if c.id != best_id:
                        c.status = CandidateStatus.FINALIST
                        self.repo.update_candidate_status(c.id, CandidateStatus.FINALIST)

                # Notify
                self.dispatcher.draft_awaiting_review(
                    run.id, self.program.name, draft.id, best.title
                )
            else:
                # Auto-publish
                best.status = CandidateStatus.PUBLISHED
                self.repo.update_candidate_status(best.id, CandidateStatus.PUBLISHED)

                for c in final_candidates:
                    if c.id != best_id:
                        c.status = CandidateStatus.FINALIST
                        self.repo.update_candidate_status(c.id, CandidateStatus.FINALIST)

                pub = PublicationRecord(
                    id=new_id(),
                    run_id=run.id,
                    candidate_id=best.id,
                    candidate_title=best.title,
                    abstract=f"Breakthrough candidate in {best.domain}: {best.statement[:200]}",
                    hypothesis=best.statement,
                    score_breakdown=scores[best.id].model_dump(),
                    evidence_summary=self._format_evidence_summary(evidence_packs.get(best.id)),
                    simulation_summary=self._format_sim_summary(sim_results.get(best.id)),
                    assumptions=best.assumptions,
                    uncertainties=best.risk_flags,
                    replication_priority="high" if scores[best.id].final_score > 0.8 else "medium",
                )
                self.repo.save_publication(pub)
                run.publication_id = pub.id
                run.status = RunStatus.COMPLETED
                metrics.publication_created = True
                logger.info("[%s] Published candidate: %s (score=%.3f)",
                            run.id[:8], best.title, scores[best.id].final_score)
        else:
            run.status = RunStatus.COMPLETED_NO_PUBLICATION
            logger.info("[%s] No candidates passed publication gate", run.id[:8])

        metrics.stage_durations["publication_selection"] = round(time.time() - t_step, 2)

        run.candidates_rejected = run.candidates_generated - (1 if run.publication_id else 0)
        run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.repo.save_run(run)

        # Collect candidate status counts
        for status_val in CandidateStatus:
            try:
                row = self.repo.db.execute(
                    "SELECT COUNT(*) FROM bt_candidates WHERE run_id=? AND status=?",
                    (run.id, status_val.value),
                ).fetchone()
                cnt = row[0] if row else 0
                if cnt > 0:
                    metrics.candidates_by_status[status_val.value] = cnt
            except Exception:
                pass

        metrics.total_duration_seconds = round(time.time() - t0, 2)
        self.repo.save_run_metrics(metrics)

        # Phase 4C: Finalize embedding monitoring
        try:
            self.embedding_monitor.finish_run()
        except Exception:
            pass

        # Phase 4C: Save calibration diagnostics
        try:
            pub_fail_reasons = []
            for c_id, passed in publication_passed.items():
                if not passed:
                    cand = self.repo.get_candidate(c_id)
                    if cand:
                        pub_fail_reasons.append(cand.get("rejection_reason", "")[:100])

            df_scores = []
            for df in domain_fit_results.values():
                if hasattr(df, "domain_fit_score"):
                    df_scores.append(df.domain_fit_score)

            self.repo.save_calibration_diagnostic({
                "run_id": run.id,
                "lexical_block_count": metrics.novelty_fail_count,
                "embedding_block_count": sum(
                    1 for nr_id, nr in novelty_results.items()
                    if hasattr(nr, 'explanation') and 'Embedding similarity' in (nr.explanation or '')
                ),
                "domain_fit_fail_count": sum(
                    1 for df in domain_fit_results.values()
                    if hasattr(df, 'passed') and not df.passed
                ),
                "domain_fit_mean_score": (
                    sum(df_scores) / len(df_scores) if df_scores else 0.0
                ),
                "publication_pass_count": sum(1 for v in publication_passed.values() if v),
                "publication_fail_count": sum(1 for v in publication_passed.values() if not v),
                "publication_fail_reasons": pub_fail_reasons[:5],
                "draft_count": 1 if metrics.draft_created else 0,
                "candidate_count": run.candidates_generated,
                "active_thresholds": {
                    "publication_threshold": self.program.publication_threshold,
                    "embedding_block": self.embedding_novelty.similarity_threshold,
                    "embedding_warn": self.embedding_novelty.warn_threshold,
                    "domain_fit_min": self.domain_fit_evaluator._min_score_override or 0.25,
                    "corpus_maintenance": {
                        "archived_by_age": archival_stats.get("archived_by_age", 0),
                        "total_archived_this_run": archival_stats.get("total_archived", 0),
                        "active_corpus_size": self.corpus_manager.get_active_count(self.program.domain),
                    },
                },
            })
        except Exception:
            pass

        # Phase 4D: Advance sub-domain rotation after run completes
        try:
            self.diversity_engine.advance_rotation(self.program.domain)
        except Exception as e:
            logger.debug("Rotation advance failed (non-fatal): %s", e)

        # Notify completion
        self.dispatcher.run_completed(
            run.id, self.program.name, run.status.value,
            publication_id=run.publication_id,
            draft_created=metrics.draft_created,
        )

        return run

    def _deduplicate(
        self, run: RunRecord, candidates: list[CandidateHypothesis]
    ) -> list[CandidateHypothesis]:
        passing = []
        for c in candidates:
            is_dup, reason = self.memory.is_near_duplicate(
                c, exclude_run_id=run.id
            )
            if is_dup:
                self._reject(run, c, CandidateStatus.DEDUP_REJECTED, reason)
            else:
                passing.append(c)
        return passing

    def _run_hypothesis_gate(
        self, run: RunRecord, candidates: list[CandidateHypothesis]
    ) -> list[CandidateHypothesis]:
        prior_stmts = self.memory.get_prior_statements(
            self.program.domain, exclude_run_id=run.id
        )
        passing = []
        for c in candidates:
            decision = run_hypothesis_harness(c, prior_stmts)
            self.repo.save_harness_decision(decision)
            if decision.passed:
                passing.append(c)
            else:
                self._reject(run, c, CandidateStatus.HYPOTHESIS_FAILED,
                             f"Hypothesis harness: {', '.join(decision.failed_rules)}",
                             "hypothesis_legality", decision.failed_rules)
        return passing

    def _run_evidence_gate(
        self,
        run: RunRecord,
        candidates: list[CandidateHypothesis],
        evidence: list,
        evidence_packs: dict[str, EvidencePack],
    ) -> list[CandidateHypothesis]:
        passing = []
        for c in candidates:
            # Phase 4B: Improved evidence linking
            # First try direct ref matching, then fall back to ranked matching
            items = []
            if c.evidence_refs:
                items = [e for e in evidence if e.id in c.evidence_refs]

            if not items and evidence:
                # Use ranked evidence matching based on mechanism keywords
                ranked = rank_evidence(
                    evidence,
                    domain=self.program.domain,
                    mechanism=c.mechanism,
                )
                items = [item for item, _ in ranked[:max(self.program.evidence_minimum, 2)]]
                # Update evidence_refs to reflect actual links
                c.evidence_refs = [e.id for e in items]

                # Persist ranking details
                for item, detail in ranked[:5]:
                    try:
                        self.repo.save_evidence_ranking(
                            candidate_id=c.id,
                            evidence_id=item.id,
                            composite_score=detail.get("composite_score", 0),
                            rank_explanation=detail.get("rank_explanation", ""),
                        )
                    except Exception:
                        pass  # v003 migration may not be applied

            pack = EvidencePack(
                candidate_id=c.id,
                items=items,
                source_diversity_count=len(set(i.source_id for i in items)),
            )
            self.repo.save_evidence_pack(pack)
            evidence_packs[c.id] = pack

            decision = run_evidence_harness(pack, self.program.evidence_minimum)
            self.repo.save_harness_decision(decision)
            if decision.passed:
                passing.append(c)
            else:
                self._reject(run, c, CandidateStatus.EVIDENCE_FAILED,
                             f"Evidence harness: {', '.join(decision.failed_rules)}",
                             "evidence_legality", decision.failed_rules)
        return passing

    def _run_novelty_gate(
        self,
        run: RunRecord,
        candidates: list[CandidateHypothesis],
        evidence: list,
        novelty_results: dict,
    ) -> list[CandidateHypothesis]:
        """Novelty gate — lexical (Phase 3) + embedding (Phase 4B)."""
        # Build prior texts for embedding novelty — filtered to active corpus only (Phase 4D)
        prior_texts = []
        try:
            domain = candidates[0].domain if candidates else ""
            prior_cands = self.novelty_engine._get_prior_candidates(domain, run.id)
            # Phase 4D: filter to active (non-archived) candidates only
            active_ids = self.corpus_manager.get_active_candidate_ids(domain)
            total_prior = len(prior_cands)
            active_prior = [pc for pc in prior_cands if pc.get("id") in active_ids] if active_ids else prior_cands
            logger.info(
                "[%s] Novelty corpus: total_prior=%d active=%d (archived excluded=%d)",
                run.id[:8], total_prior, len(active_prior), total_prior - len(active_prior),
            )
            for pc in active_prior:
                prior_texts.append({
                    "title": pc.get("title", ""),
                    "text": f"{pc.get('title', '')}. {pc.get('statement', '')}. {pc.get('mechanism', '')}",
                    "source": "local_candidate",
                    "source_id": pc.get("id", ""),
                })
        except Exception:
            pass

        passing = []
        for c in candidates:
            # Lexical novelty
            result = self.novelty_engine.evaluate(
                candidate=c,
                retrieved_evidence=evidence,
                exclude_run_id=run.id,
            )
            self.repo.save_novelty_check(result)
            novelty_results[c.id] = result

            # Embedding novelty (Phase 4B)
            emb_detail = self.embedding_novelty.evaluate(
                candidate=c,
                prior_texts=prior_texts,
                retrieved_evidence=evidence,
            )
            # Phase 4C: Record in embedding monitor
            self.embedding_monitor.record_evaluation(emb_detail)
            # Persist embedding novelty detail
            try:
                self.repo.save_embedding_novelty({
                    "candidate_id": c.id,
                    **emb_detail.to_dict(),
                })
            except Exception:
                pass  # v003 migration may not be applied yet

            # Combined decision: fail if either lexical hard-fail or embedding block
            blocked = False
            if result.decision == NoveltyDecision.FAIL:
                blocked = True
            elif emb_detail.blocked_by_prior_art:
                blocked = True
                result.explanation += (
                    f" | Embedding similarity={emb_detail.embedding_similarity_max:.3f} "
                    f"exceeds threshold (semantic near-duplicate)"
                )

            # Save gate diagnostic
            try:
                self.repo.save_gate_diagnostic(
                    run_id=run.id, candidate_id=c.id, gate_name="novelty",
                    passed=not blocked, score=result.novelty_score,
                    reasons=result.overlap_reasons[:5] + (
                        [f"embedding_sim={emb_detail.embedding_similarity_max:.3f}"]
                        if emb_detail.embedding_similarity_max > 0 else []
                    ),
                )
            except Exception:
                pass

            if blocked:
                self._reject(run, c, CandidateStatus.NOVELTY_FAILED,
                             f"Novelty gate: {result.explanation[:200]}",
                             "novelty_gate", result.overlap_reasons[:5])
            else:
                if result.decision == NoveltyDecision.WARN:
                    logger.info("[%s] Novelty warning for '%s': %s",
                                run.id[:8], c.title[:40], result.explanation[:100])
                passing.append(c)
        return passing

    def _run_domain_fit_gate(
        self,
        run: RunRecord,
        candidates: list[CandidateHypothesis],
        evidence: list,
        domain_fit_results: dict,
    ) -> list[CandidateHypothesis]:
        """Phase 4B: Domain-fit gate — reject candidates that don't fit the program."""
        passing = []
        for c in candidates:
            fit = self.domain_fit_evaluator.evaluate(
                candidate=c,
                program=self.program,
                evidence=evidence,
            )
            domain_fit_results[c.id] = fit

            # Persist domain fit
            try:
                self.repo.save_domain_fit(fit.to_dict())
            except Exception:
                pass  # v003 migration may not be applied yet

            # Save gate diagnostic
            try:
                self.repo.save_gate_diagnostic(
                    run_id=run.id, candidate_id=c.id, gate_name="domain_fit",
                    passed=fit.passed, score=fit.domain_fit_score,
                    reasons=fit.mismatch_flags[:5] if not fit.passed else fit.relevance_reasons[:3],
                )
            except Exception:
                pass

            if not fit.passed:
                self._reject(run, c, CandidateStatus.PUBLICATION_FAILED,
                             f"Domain fit failed: score={fit.domain_fit_score:.2f}, "
                             f"flags={', '.join(fit.mismatch_flags[:3])}",
                             "domain_fit", fit.mismatch_flags[:5])
            else:
                passing.append(c)
        return passing

    def _run_simulation_gate(
        self,
        run: RunRecord,
        candidates: list[CandidateHypothesis],
        evidence_packs: dict[str, EvidencePack],
        sim_results: dict[str, SimulationResult],
    ) -> list[CandidateHypothesis]:
        passing = []
        for c in candidates:
            spec = SimulationSpec(
                candidate_id=c.id,
                simulator=self.program.allowed_simulators[0] if self.program.allowed_simulators else "mock",
                objective=f"Validate: {c.expected_outcome[:100]}",
                parameters={"hypothesis_hash": hash(c.statement) % 10000},
                estimated_runtime_minutes=5.0,
            )
            self.repo.save_simulation_spec(spec)

            decision = run_simulation_harness(
                spec,
                runtime_budget_minutes=self.program.runtime_budget_minutes,
                allowed_simulators=self.program.allowed_simulators,
            )
            self.repo.save_harness_decision(decision)

            if not decision.passed:
                self._reject(run, c, CandidateStatus.SIMULATION_FAILED,
                             f"Simulation harness: {', '.join(decision.failed_rules)}",
                             "simulation_legality", decision.failed_rules)
                continue

            try:
                result = self.simulator.run(spec)
                self.repo.save_simulation_result(result)
                sim_results[c.id] = result
                passing.append(c)
            except Exception as e:
                self._reject(run, c, CandidateStatus.SIMULATION_FAILED,
                             f"Simulation execution error: {e}",
                             "simulation_execution")
        return passing

    def _reject(
        self,
        run: RunRecord,
        candidate: CandidateHypothesis,
        status: CandidateStatus,
        reason: str,
        harness_name: str = "",
        failed_rules: list[str] | None = None,
    ) -> None:
        candidate.status = status
        candidate.rejection_reason = reason
        self.repo.update_candidate_status(candidate.id, status, reason)
        self.repo.save_rejection(
            run_id=run.id,
            candidate_id=candidate.id,
            candidate_title=candidate.title,
            status=status,
            reason=reason,
            harness_name=harness_name,
            failed_rules=failed_rules,
        )

    @staticmethod
    def _format_evidence_summary(pack: EvidencePack | None) -> str:
        if not pack or not pack.items:
            return "No evidence attached."
        lines = []
        for i, item in enumerate(pack.items, 1):
            lines.append(f"{i}. [{item.citation}] \"{item.quote[:150]}...\"")
        return "\n".join(lines)

    @staticmethod
    def _format_sim_summary(result: SimulationResult | None) -> str:
        if not result:
            return "Not simulated."
        return f"Status: {result.status.value}. {result.pass_fail_summary}"
