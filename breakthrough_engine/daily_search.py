"""Daily quality-first search ladder for Breakthrough Engine Phase 6.

The ladder is a 5-stage structured campaign to find the best candidate of
the day. Each stage has explicit stopping rules to avoid wasting compute.

Two modes:
- BENCHMARK: fixed stage budgets, offline-safe, for policy comparison
- PRODUCTION: wall-clock budget, real LLM + embedding, quality-first

Stage flow:
  1. Broad exploration (N runs, collect all finalists)
  2. Shortlist (top-K by score)
  3. Falsification (stress-test shortlisted candidates)
  4. Review packet preparation
  5. Daily champion selection

Each stage may stop early due to:
  - max_trials reached
  - max_wall_clock_seconds reached
  - posterior dominance detected
  - abandon_floor: all candidates below minimum quality
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .db import Repository, init_db
from .falsification import FalsificationEngine, FalsificationSummary
from .models import (
    CandidateHypothesis,
    ResearchProgram,
    RunMode,
    RunRecord,
    RunStatus,
    new_id,
)
from .policy_registry import PolicyConfig, PolicyRegistry, PHASE5_CHAMPION_ID
from .review_cockpit import ReviewCockpit, ReviewDecisionPacket
from .reward_logger import RewardLogger
from .scoring import rank_candidates, score_candidate

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Stage configuration
# ---------------------------------------------------------------------------

@dataclass
class StageConfig:
    """Per-stage stopping rules and quality thresholds."""
    max_trials: int = 3
    min_score_to_advance: float = 0.40
    max_wall_clock_seconds: int = 300
    early_stop_if_posterior_dominates: bool = True
    abandon_floor: float = 0.30
    # If top candidate's posterior mean exceeds others by this margin, stop early
    early_stop_margin: float = 0.15


@dataclass
class LadderConfig:
    """Configuration for a daily search campaign."""
    mode: str = "benchmark"    # "benchmark" | "production"
    program_name: str = "cross_domain_shadow"
    policy_variants: list = field(default_factory=list)  # empty = use champion only

    # Per-stage configs
    stage1: StageConfig = field(default_factory=lambda: StageConfig(
        max_trials=3, min_score_to_advance=0.40,
        max_wall_clock_seconds=300, abandon_floor=0.30
    ))
    stage2_shortlist_size: int = 3
    stage3: StageConfig = field(default_factory=lambda: StageConfig(
        max_trials=3, min_score_to_advance=0.50,
        max_wall_clock_seconds=120, abandon_floor=0.40
    ))
    stage4_review_prep: bool = True

    # Production override (wall clock for whole campaign)
    production_wall_clock_budget_minutes: int = 120


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class LadderStageResult:
    """Result of one stage execution."""
    stage_name: str
    trials_attempted: int = 0
    candidates_advanced: int = 0
    candidates_abandoned: int = 0
    best_score: float = 0.0
    best_candidate_id: str = ""
    stop_reason: str = "completed"  # completed|budget_exhausted|early_stopped|abandoned
    elapsed_seconds: float = 0.0
    details: dict = field(default_factory=dict)


@dataclass
class DailyCampaignResult:
    """Full result of a daily search campaign."""
    campaign_id: str = ""
    mode: str = "benchmark"
    policy_used: str = ""
    daily_champion_id: str = ""
    daily_champion_title: str = ""
    champion_selection_rationale: str = ""

    ladder_stages: list = field(default_factory=list)  # list[LadderStageResult]
    policy_trials_attempted: int = 0
    domain_pairs_tried: list = field(default_factory=list)
    bridge_mechanisms_tried: list = field(default_factory=list)

    total_candidates_generated: int = 0
    total_blocked: int = 0
    total_shortlisted: int = 0

    elapsed_seconds: float = 0.0
    started_at: str = ""
    completed_at: str = ""

    review_packets: list = field(default_factory=list)  # ReviewDecisionPacket


# ---------------------------------------------------------------------------
# DailySearchLadder
# ---------------------------------------------------------------------------

class DailySearchLadder:
    """Runs a structured 5-stage daily search campaign."""

    def __init__(
        self,
        falsification_engine: Optional[FalsificationEngine] = None,
        review_cockpit: Optional[ReviewCockpit] = None,
        reward_logger: Optional[RewardLogger] = None,
    ):
        self.falsification_engine = falsification_engine or FalsificationEngine()
        self.review_cockpit = review_cockpit or ReviewCockpit()
        self.reward_logger = reward_logger or RewardLogger()

    def run_campaign(
        self,
        repo: Repository,
        config: Optional[LadderConfig] = None,
        policy_registry: Optional[PolicyRegistry] = None,
        program: Optional[ResearchProgram] = None,
    ) -> DailyCampaignResult:
        """Run a complete daily search campaign."""
        if config is None:
            config = LadderConfig()

        campaign_id = new_id()
        t0 = time.time()
        result = DailyCampaignResult(
            campaign_id=campaign_id,
            mode=config.mode,
            started_at=_utcnow(),
        )

        # Determine policy to use
        champion_policy = None
        if policy_registry is not None:
            try:
                champion_policy = policy_registry.get_champion()
                result.policy_used = champion_policy.id
            except Exception as e:
                logger.warning("Could not load champion policy: %s", e)
        if champion_policy is None:
            from .policy_registry import _default_champion
            champion_policy = _default_champion()
            result.policy_used = champion_policy.id

        # Load program if not provided
        if program is None:
            program = self._load_program(config.program_name, config.mode)

        # ---- Stage 1: Broad Exploration ----
        stage1_result, all_finalists = self._stage1_exploration(
            repo, program, champion_policy, config
        )
        result.ladder_stages.append(stage1_result)
        result.total_candidates_generated = stage1_result.trials_attempted * max(
            program.candidate_budget, 1
        )
        result.policy_trials_attempted = stage1_result.trials_attempted

        if stage1_result.stop_reason == "abandoned":
            result.completed_at = _utcnow()
            result.elapsed_seconds = time.time() - t0
            result.champion_selection_rationale = "Stage 1 abandoned — all candidates below quality floor"
            self._save_campaign(repo, config, result)
            return result

        # ---- Stage 2: Shortlist ----
        shortlisted = self._stage2_shortlist(all_finalists, config.stage2_shortlist_size)
        result.total_shortlisted = len(shortlisted)
        stage2_result = LadderStageResult(
            stage_name="stage2_shortlist",
            trials_attempted=0,
            candidates_advanced=len(shortlisted),
            candidates_abandoned=max(0, len(all_finalists) - len(shortlisted)),
            best_score=max((s for _, s in shortlisted), default=0.0),
            stop_reason="completed",
        )
        result.ladder_stages.append(stage2_result)

        if not shortlisted:
            result.completed_at = _utcnow()
            result.elapsed_seconds = time.time() - t0
            result.champion_selection_rationale = "No candidates advanced past shortlist"
            self._save_campaign(repo, config, result)
            return result

        # ---- Stage 3: Falsification ----
        stage3_result, falsified = self._stage3_falsification(repo, shortlisted, config)
        result.ladder_stages.append(stage3_result)

        if not falsified:
            # Use all shortlisted even if falsification found risks
            falsified = shortlisted
            logger.warning("All candidates had high falsification risk; proceeding anyway")

        # ---- Stage 4: Review Packet Preparation ----
        packets = []
        if config.stage4_review_prep:
            stage4_result, packets = self._stage4_review_prep(repo, falsified, campaign_id)
            result.ladder_stages.append(stage4_result)
        else:
            result.ladder_stages.append(LadderStageResult(
                stage_name="stage4_review_prep", stop_reason="skipped"
            ))

        # ---- Stage 5: Champion Selection ----
        stage5_result, champion, champion_score, rationale = self._stage5_select_champion(
            falsified, packets
        )
        result.ladder_stages.append(stage5_result)
        result.review_packets = packets

        if champion is not None:
            result.daily_champion_id = champion.id
            result.daily_champion_title = champion.title
            result.champion_selection_rationale = rationale
            logger.info(
                "Daily champion selected: '%s' (score=%.3f)",
                champion.title[:50], champion_score,
            )
        else:
            result.champion_selection_rationale = "No champion selected — all candidates failed stages"

        result.completed_at = _utcnow()
        result.elapsed_seconds = time.time() - t0

        # Persist campaign record
        self._save_campaign(repo, config, result)
        return result

    # ---------------------
    # Stage implementations
    # ---------------------

    def _stage1_exploration(
        self,
        repo: Repository,
        program: ResearchProgram,
        policy: PolicyConfig,
        config: LadderConfig,
    ) -> tuple:
        """Stage 1: Broad exploration — run N trials, collect all finalists."""
        t0 = time.time()
        stage = config.stage1
        all_finalists: list = []   # list of (CandidateHypothesis, final_score)
        trials_attempted = 0

        for trial_idx in range(stage.max_trials):
            elapsed = time.time() - t0
            if elapsed > stage.max_wall_clock_seconds:
                logger.info("Stage 1: wall clock budget reached at trial %d", trial_idx)
                stop_reason = "budget_exhausted"
                break

            logger.info("Stage 1: trial %d / %d", trial_idx + 1, stage.max_trials)
            run_record, finalists = self._run_single_trial(repo, program, policy)
            trials_attempted += 1

            all_finalists.extend(finalists)

            # Early stop check
            if stage.early_stop_if_posterior_dominates and self._should_early_stop(
                all_finalists, stage.early_stop_margin
            ):
                logger.info("Stage 1: early stop — posterior dominance detected")
                stop_reason = "early_stopped"
                break
        else:
            stop_reason = "completed"

        # Filter by min_score_to_advance
        advanced = [(c, s) for c, s in all_finalists if s >= stage.min_score_to_advance]
        abandoned = len(all_finalists) - len(advanced)

        if not advanced:
            if all_finalists:
                max_score = max(s for _, s in all_finalists)
                if max_score < stage.abandon_floor:
                    stop_reason = "abandoned"
            else:
                stop_reason = "abandoned"

        elapsed = time.time() - t0
        best_score = max((s for _, s in advanced), default=0.0)
        best_cid = ""
        if advanced:
            best_c, _ = max(advanced, key=lambda x: x[1])
            best_cid = best_c.id

        stage_result = LadderStageResult(
            stage_name="stage1_exploration",
            trials_attempted=trials_attempted,
            candidates_advanced=len(advanced),
            candidates_abandoned=abandoned,
            best_score=best_score,
            best_candidate_id=best_cid,
            stop_reason=stop_reason,
            elapsed_seconds=elapsed,
            details={"total_collected": len(all_finalists)},
        )
        return stage_result, advanced

    def _stage2_shortlist(
        self,
        finalists: list,
        shortlist_size: int,
    ) -> list:
        """Stage 2: Keep top-K candidates by score."""
        sorted_finalists = sorted(finalists, key=lambda x: x[1], reverse=True)
        return sorted_finalists[:shortlist_size]

    def _stage3_falsification(
        self,
        repo: Repository,
        shortlisted: list,
        config: LadderConfig,
    ) -> tuple:
        """Stage 3: Falsify shortlisted candidates."""
        t0 = time.time()
        stage = config.stage3
        passed: list = []
        failed: list = []

        for candidate, score in shortlisted[:stage.max_trials]:
            elapsed = time.time() - t0
            if elapsed > stage.max_wall_clock_seconds:
                logger.info("Stage 3: wall clock reached, skipping remaining candidates")
                # Pass remaining without falsification
                passed.extend(
                    (c, s) for c, s in shortlisted[len(passed) + len(failed):]
                )
                break

            try:
                # Get evidence pack if available
                evidence_pack = self._get_evidence_pack(repo, candidate)
                synthesis_context = self._get_synthesis_context(repo, candidate)
                falsification_summary = self.falsification_engine.evaluate(
                    candidate, evidence_pack, synthesis_context
                )
                # Save to DB
                self.falsification_engine.save_summary(repo, falsification_summary)

                if falsification_summary.falsification_passed and score >= stage.min_score_to_advance:
                    passed.append((candidate, score))
                else:
                    failed.append((candidate, score, falsification_summary.overall_falsification_risk))
                    logger.info(
                        "Stage 3: candidate '%s' failed (risk=%s, score=%.3f)",
                        candidate.title[:40],
                        falsification_summary.overall_falsification_risk,
                        score,
                    )
            except Exception as e:
                logger.warning("Stage 3: falsification error for %s: %s", candidate.id, e)
                passed.append((candidate, score))  # Don't block on error

        elapsed = time.time() - t0

        # Determine stop reason
        if not passed and not failed:
            stop_reason = "abandoned"
        elif len(passed) == 0:
            stop_reason = "abandoned"
        else:
            stop_reason = "completed"

        stage_result = LadderStageResult(
            stage_name="stage3_falsification",
            trials_attempted=len(shortlisted),
            candidates_advanced=len(passed),
            candidates_abandoned=len(failed),
            best_score=max((s for _, s in passed), default=0.0),
            stop_reason=stop_reason,
            elapsed_seconds=elapsed,
            details={"failed_details": [
                {"title": c.title[:40], "risk": risk}
                for c, _, risk in failed
            ]},
        )
        return stage_result, passed

    def _stage4_review_prep(
        self,
        repo: Repository,
        candidates_with_scores: list,
        campaign_id: str,
    ) -> tuple:
        """Stage 4: Build review packets for surviving candidates."""
        t0 = time.time()
        packets = []

        for candidate, score in candidates_with_scores:
            try:
                evidence_pack = self._get_evidence_pack(repo, candidate)
                synthesis_fit = self._get_synthesis_fit(repo, candidate)
                novelty_result = self._get_novelty_result(repo, candidate)
                candidate_score = repo.get_score(candidate.id)
                falsification_summary = self.falsification_engine.load_summary(repo, candidate.id)

                packet = self.review_cockpit.build_packet(
                    candidate=candidate,
                    evidence_pack=evidence_pack,
                    synthesis_fit=synthesis_fit,
                    novelty_result=novelty_result,
                    candidate_score=candidate_score,
                    falsification_summary=falsification_summary,
                    campaign_id=campaign_id,
                )
                packets.append(packet)
            except Exception as e:
                logger.warning("Stage 4: packet build error for %s: %s", candidate.id, e)

        elapsed = time.time() - t0
        stage_result = LadderStageResult(
            stage_name="stage4_review_prep",
            trials_attempted=len(candidates_with_scores),
            candidates_advanced=len(packets),
            candidates_abandoned=len(candidates_with_scores) - len(packets),
            stop_reason="completed",
            elapsed_seconds=elapsed,
        )
        return stage_result, packets

    def _stage5_select_champion(
        self,
        candidates_with_scores: list,
        packets: list,
    ) -> tuple:
        """Stage 5: Select the daily champion."""
        t0 = time.time()

        if not candidates_with_scores:
            return LadderStageResult(
                stage_name="stage5_champion_selection",
                stop_reason="abandoned",
            ), None, 0.0, "No candidates available"

        # Build packet-based lookup if available
        packet_by_cid = {p.candidate_id: p for p in packets} if packets else {}

        # Sort by: falsification_passed DESC, final_score DESC
        def sort_key(cs):
            c, s = cs
            packet = packet_by_cid.get(c.id)
            falsification_passed = True
            if packet and packet.falsification_summary:
                falsification_passed = packet.falsification_summary.get("falsification_passed", True)
            return (int(falsification_passed), s)

        ranked = sorted(candidates_with_scores, key=sort_key, reverse=True)
        champion, champion_score = ranked[0]
        runner_ups = ranked[1:]

        champion_packet = packet_by_cid.get(champion.id)
        if champion_packet:
            rationale = (
                f"Score {champion_score:.3f}, {champion_packet.recommended_action}, "
                f"beat {len(runner_ups)} runner-up(s). "
                + champion_packet.recommendation_rationale
            )
        else:
            rationale = (
                f"Score {champion_score:.3f}, beat {len(runner_ups)} runner-up(s)."
            )

        elapsed = time.time() - t0
        stage_result = LadderStageResult(
            stage_name="stage5_champion_selection",
            trials_attempted=len(candidates_with_scores),
            candidates_advanced=1,
            candidates_abandoned=len(runner_ups),
            best_score=champion_score,
            best_candidate_id=champion.id,
            stop_reason="completed",
            elapsed_seconds=elapsed,
        )
        return stage_result, champion, champion_score, rationale

    # ---------------------
    # Helpers
    # ---------------------

    def _run_single_trial(
        self,
        repo: Repository,
        program: ResearchProgram,
        policy: PolicyConfig,
    ) -> tuple:
        """Run one orchestrator trial and return (RunRecord, finalists).

        finalists = list of (CandidateHypothesis, final_score)
        """
        from .benchmark import BenchmarkCandidateGenerator, _make_deterministic_orchestrator
        from .benchmark import golden_high_quality, golden_publishable_finalist
        from .benchmark import golden_overconfident, golden_evidence_poor
        from .memory import RunMemory
        from .novelty import NoveltyEngine
        from .embedding_monitor import EmbeddingMonitor
        from .diversity import DiversityEngine
        from .corpus_manager import CorpusManager
        from .synthesis import SynthesisEngine
        from .models import CandidateStatus

        # Use the shared repo (not a new in-memory one) for production mode
        # For benchmark/demo, create isolated repo
        use_isolated = program.mode in (RunMode.DETERMINISTIC_TEST,)

        if use_isolated:
            trial_db = init_db(in_memory=True)
            trial_repo = Repository(trial_db)
        else:
            trial_repo = repo

        # Apply policy-specific overrides
        trial_program = self._apply_policy(program, policy)

        if program.mode == RunMode.DETERMINISTIC_TEST:
            # Offline-safe benchmark: use fake generator and in-memory repo
            gen = BenchmarkCandidateGenerator([
                golden_high_quality(),
                golden_publishable_finalist(),
                golden_overconfident(),
                golden_evidence_poor(),
            ])
            orch, _ = _make_deterministic_orchestrator(
                program=trial_program,
                generator=gen,
            )
            orch.repo = trial_repo
            orch.memory = RunMemory(trial_repo.db)
            orch.novelty_engine = NoveltyEngine(trial_repo.db)
            orch.embedding_monitor = EmbeddingMonitor(trial_repo)
            orch.diversity_engine = DiversityEngine(trial_repo)
            orch.corpus_manager = CorpusManager(trial_repo)
            orch.synthesis_engine = SynthesisEngine(trial_repo)
        else:
            # Production mode: use real Ollama generator and shared repo
            from .orchestrator import BreakthroughOrchestrator
            orch = BreakthroughOrchestrator(
                program=trial_program,
                repo=trial_repo,
            )

        run_record = orch.run()

        # Collect finalists with scores
        finalists = []
        for c in trial_repo.list_candidates_for_run(run_record.id):
            status = c.get("status", "")
            if status in (
                CandidateStatus.FINALIST.value,
                CandidateStatus.PUBLISHED.value,
                CandidateStatus.DRAFT_PENDING_REVIEW.value,
            ):
                score_row = trial_repo.get_score(c["id"])
                fs = float(score_row["final_score"]) if score_row else 0.0

                # Reconstruct candidate object
                import json
                from .models import _utcnow as _m_utcnow
                candidate = CandidateHypothesis(
                    id=c["id"],
                    run_id=run_record.id,
                    title=c["title"],
                    domain=c["domain"],
                    statement=c["statement"],
                    mechanism=c["mechanism"],
                    expected_outcome=c["expected_outcome"],
                    testability_window_hours=c.get("testability_window_hours", 24.0),
                    novelty_notes=c.get("novelty_notes", ""),
                    assumptions=json.loads(c.get("assumptions") or "[]"),
                    risk_flags=json.loads(c.get("risk_flags") or "[]"),
                    evidence_refs=json.loads(c.get("evidence_refs") or "[]"),
                )
                finalists.append((candidate, fs))

                # Copy to shared repo if isolated
                if use_isolated:
                    try:
                        trial_repo.db.execute(
                            "INSERT OR IGNORE INTO bt_candidates SELECT * FROM bt_candidates WHERE id=?",
                            (c["id"],),
                        )
                    except Exception:
                        pass

        return run_record, finalists

    def _should_early_stop(
        self,
        finalists: list,
        margin: float,
    ) -> bool:
        """Return True if top candidate's score dominates all others by margin."""
        if len(finalists) < 2:
            return False
        scores = sorted([s for _, s in finalists], reverse=True)
        return (scores[0] - scores[1]) > margin

    def _apply_policy(
        self,
        program: ResearchProgram,
        policy: PolicyConfig,
    ) -> ResearchProgram:
        """Return a copy of program with policy overrides applied."""
        if policy.scoring_weights is not None:
            # Build a copy with overridden weights
            from dataclasses import replace
            new_weights = dict(program.scoring_weights or {})
            new_weights.update(policy.scoring_weights)
            return ResearchProgram(
                name=program.name,
                domain=program.domain,
                goal=program.goal,
                mode=program.mode,
                candidate_budget=program.candidate_budget,
                simulation_budget=program.simulation_budget,
                publication_threshold=program.publication_threshold,
                evidence_minimum=program.evidence_minimum,
                scoring_weights=new_weights,
                runtime_budget_minutes=program.runtime_budget_minutes,
                novelty_threshold=program.novelty_threshold,
                banned_claims=program.banned_claims,
                safety_constraints=program.safety_constraints,
                allowed_simulators=program.allowed_simulators,
                validation_policy=program.validation_policy,
            )
        return program

    def _load_program(self, program_name: str, mode: str) -> ResearchProgram:
        """Load program from config, or return a default."""
        try:
            from .config_loader import load_program
            return load_program(program_name)
        except Exception as e:
            logger.warning("Could not load program '%s': %s — using default", program_name, e)
            run_mode = RunMode.DETERMINISTIC_TEST if mode == "benchmark" else RunMode.PRODUCTION_SHADOW
            return ResearchProgram(
                name=program_name,
                domain="clean-energy",
                mode=run_mode,
                candidate_budget=5,
                simulation_budget=3,
                publication_threshold=0.60,
            )

    def _get_evidence_pack(self, repo, candidate: CandidateHypothesis):
        """Reconstruct evidence pack for a candidate from DB."""
        from .models import EvidencePack, EvidenceItem
        try:
            row = repo.db.execute(
                "SELECT * FROM bt_evidence_packs WHERE candidate_id=? LIMIT 1",
                (candidate.id,),
            ).fetchone()
            if row is None:
                return None
            pack_row = dict(row)
            items_rows = repo.db.execute(
                "SELECT * FROM bt_evidence_items WHERE pack_id=?",
                (pack_row["id"],),
            ).fetchall()
            items = [
                EvidenceItem(
                    id=r["id"],
                    source_type=r["source_type"],
                    source_id=r["source_id"],
                    title=r["title"],
                    quote=r["quote"],
                    citation=r["citation"],
                    relevance_score=r.get("relevance_score", 0.5),
                )
                for r in items_rows
            ]
            return EvidencePack(
                id=pack_row["id"],
                candidate_id=candidate.id,
                items=items,
                source_diversity_count=pack_row.get("source_diversity_count", 0),
            )
        except Exception as e:
            logger.debug("Could not load evidence pack for %s: %s", candidate.id, e)
            return None

    def _get_synthesis_fit(self, repo, candidate: CandidateHypothesis):
        """Load synthesis fit for a candidate."""
        try:
            return repo.get_synthesis_fit(candidate.id)
        except Exception:
            return None

    def _get_synthesis_context(self, repo, candidate: CandidateHypothesis):
        """Load synthesis context for a candidate's run."""
        try:
            return repo.get_synthesis_context(candidate.run_id)
        except Exception:
            return None

    def _get_novelty_result(self, repo, candidate: CandidateHypothesis):
        """Load novelty check for a candidate."""
        try:
            return repo.get_novelty_check(candidate.id)
        except Exception:
            return None

    def _save_campaign(
        self,
        repo: Repository,
        config: LadderConfig,
        result: DailyCampaignResult,
    ) -> None:
        """Persist campaign record to bt_daily_campaigns + bt_ladder_stages."""
        import json
        config_dict = {
            "mode": config.mode,
            "program_name": config.program_name,
            "stage2_shortlist_size": config.stage2_shortlist_size,
            "stage4_review_prep": config.stage4_review_prep,
        }
        result_dict = {
            "policy_used": result.policy_used,
            "daily_champion_id": result.daily_champion_id,
            "daily_champion_title": result.daily_champion_title,
            "champion_selection_rationale": result.champion_selection_rationale,
            "total_candidates_generated": result.total_candidates_generated,
            "total_blocked": result.total_blocked,
            "total_shortlisted": result.total_shortlisted,
            "elapsed_seconds": round(result.elapsed_seconds, 2),
        }
        try:
            repo.db.execute(
                """INSERT INTO bt_daily_campaigns
                   (id, campaign_id, mode, policy_id, champion_candidate_id,
                    config_json, result_json, started_at, completed_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    new_id(),
                    result.campaign_id,
                    result.mode,
                    result.policy_used,
                    result.daily_champion_id,
                    json.dumps(config_dict),
                    json.dumps(result_dict),
                    result.started_at,
                    result.completed_at,
                ),
            )
            for stage in result.ladder_stages:
                repo.db.execute(
                    """INSERT INTO bt_ladder_stages
                       (campaign_id, stage_name, trials_attempted, candidates_advanced,
                        candidates_abandoned, best_score, best_candidate_id,
                        stop_reason, elapsed_seconds, details_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        result.campaign_id,
                        stage.stage_name,
                        stage.trials_attempted,
                        stage.candidates_advanced,
                        stage.candidates_abandoned,
                        stage.best_score,
                        stage.best_candidate_id,
                        stage.stop_reason,
                        stage.elapsed_seconds,
                        json.dumps(stage.details),
                    ),
                )
            repo.db.commit()
        except Exception as e:
            logger.error("Failed to save campaign record: %s", e)
