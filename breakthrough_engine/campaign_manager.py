"""Autonomous campaign manager for unattended breakthrough discovery runs.

Phase 7A: Manages campaign lifecycle from preflight through execution to
artifact export. Supports pilot (bounded) and overnight (extended) profiles.

Key responsibilities:
- Campaign start/stop with durable state
- Stage progression and checkpointing
- Retry/watchdog/fail-safe behavior
- Lock protection against overlapping campaigns
- Structured artifact export
- Campaign receipt persistence to DB
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from .db import Repository, init_db
from .models import new_id
from .preflight import PreflightEngine, PreflightReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Campaign types
# ---------------------------------------------------------------------------

class CampaignStatus(str, Enum):
    PREFLIGHT = "preflight"
    RUNNING = "running"
    COMPLETED_WITH_DRAFT = "completed_with_draft"
    COMPLETED_NO_DRAFT = "completed_no_draft"
    ABORTED_PREFLIGHT = "aborted_preflight"
    ABORTED_RUNTIME = "aborted_runtime"
    ABORTED_TIMEOUT = "aborted_timeout"
    ABORTED_SIGNAL = "aborted_signal"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRIED = "retried"


@dataclass
class CampaignProfile:
    """Loaded campaign profile from YAML."""
    profile_name: str = "pilot_30m"
    description: str = ""
    profile_type: str = "pilot"  # "pilot" | "overnight"
    domain: str = "clean-energy"
    program_name: str = "clean_energy"
    mode: str = "production"
    wall_clock_budget_minutes: int = 30
    candidate_trial_budget: int = 5
    policy_trial_budget: int = 3
    stage1_max_trials: int = 3
    stage1_min_score: float = 0.40
    stage1_wall_clock: int = 600
    stage1_abandon_floor: float = 0.30
    stage1_early_stop_margin: float = 0.15
    stage2_shortlist_size: int = 3
    stage3_max_trials: int = 3
    stage3_min_score: float = 0.50
    stage3_wall_clock: int = 180
    stage3_abandon_floor: float = 0.40
    stage4_review_prep: bool = True
    falsification_enabled: bool = True
    falsification_strict: bool = False
    # FIX (7D): When True, all finalists are falsified (not just shortlisted top-K)
    falsify_all_finalists: bool = False
    review_packet_generation: bool = True
    export_artifacts: bool = True
    max_retries_per_stage: int = 2
    retry_delay_seconds: int = 5
    health_min_candidates: int = 3
    health_min_stages: int = 3
    health_max_stage_failure_rate: float = 0.5
    health_max_retry_count: int = 3
    diagnostic_rich: bool = True
    verbose_logging: bool = True


@dataclass
class CampaignReceipt:
    """Durable record of a campaign execution."""
    campaign_id: str = ""
    profile_name: str = ""
    profile_type: str = ""
    status: str = CampaignStatus.PREFLIGHT.value
    config_snapshot: dict = field(default_factory=dict)
    preflight_report: dict = field(default_factory=dict)
    stage_events: list = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    elapsed_seconds: float = 0.0
    champion_candidate_id: str = ""
    champion_candidate_title: str = ""
    draft_id: str = ""
    failure_reason: str = ""
    total_candidates_generated: int = 0
    total_candidates_blocked: int = 0
    total_shortlisted: int = 0
    policy_trials_attempted: int = 0
    retries_used: int = 0
    artifact_paths: list = field(default_factory=list)
    health_summary: dict = field(default_factory=dict)
    embedding_provider: str = "MockEmbeddingProvider"

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "profile_name": self.profile_name,
            "profile_type": self.profile_type,
            "status": self.status,
            "config_snapshot": self.config_snapshot,
            "preflight_report": self.preflight_report,
            "stage_events": self.stage_events,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "champion_candidate_id": self.champion_candidate_id,
            "champion_candidate_title": self.champion_candidate_title,
            "draft_id": self.draft_id,
            "failure_reason": self.failure_reason,
            "total_candidates_generated": self.total_candidates_generated,
            "total_candidates_blocked": self.total_candidates_blocked,
            "total_shortlisted": self.total_shortlisted,
            "policy_trials_attempted": self.policy_trials_attempted,
            "retries_used": self.retries_used,
            "artifact_paths": self.artifact_paths,
            "health_summary": self.health_summary,
            "embedding_provider": self.embedding_provider,
        }


@dataclass
class StageEvent:
    """One stage execution record."""
    stage_name: str
    status: str = StageStatus.PENDING.value
    started_at: str = ""
    completed_at: str = ""
    elapsed_seconds: float = 0.0
    retries: int = 0
    error_message: str = ""
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "stage_name": self.stage_name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "retries": self.retries,
            "error_message": self.error_message,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Campaign lock
# ---------------------------------------------------------------------------

class CampaignLock:
    """File-based lock to prevent overlapping campaigns."""

    def __init__(self, lock_dir: Optional[str] = None):
        self.lock_dir = lock_dir or os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
        self.lock_path = os.path.join(self.lock_dir, "campaign.lock")

    def acquire(self, campaign_id: str) -> bool:
        """Try to acquire lock. Returns True if successful."""
        os.makedirs(self.lock_dir, exist_ok=True)
        if os.path.exists(self.lock_path):
            try:
                with open(self.lock_path) as f:
                    info = json.loads(f.read())
                pid = info.get("pid", 0)
                # Check if the process is still alive
                if pid and self._is_pid_alive(pid):
                    logger.warning(
                        "Campaign lock held by PID %d (campaign %s)",
                        pid, info.get("campaign_id", "unknown"),
                    )
                    return False
                else:
                    logger.info("Stale lock found (PID %d dead), removing", pid)
                    os.unlink(self.lock_path)
            except (json.JSONDecodeError, IOError):
                logger.warning("Corrupt lock file, removing")
                os.unlink(self.lock_path)

        try:
            lock_info = {
                "campaign_id": campaign_id,
                "pid": os.getpid(),
                "acquired_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            with open(self.lock_path, "w") as f:
                f.write(json.dumps(lock_info))
            return True
        except IOError as e:
            logger.error("Failed to write lock file: %s", e)
            return False

    def release(self) -> None:
        """Release the campaign lock."""
        try:
            if os.path.exists(self.lock_path):
                os.unlink(self.lock_path)
        except IOError as e:
            logger.warning("Failed to remove lock file: %s", e)

    def _is_pid_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

RETRYABLE_ERRORS = {
    "ollama_timeout": ["timeout", "timed out", "connect timeout"],
    "db_lock": ["database is locked", "locked"],
    "file_write": ["permission denied", "no space left"],
}


def _is_retryable(error: Exception) -> bool:
    """Check if an error is retryable."""
    error_str = str(error).lower()
    for patterns in RETRYABLE_ERRORS.values():
        for pattern in patterns:
            if pattern in error_str:
                return True
    return False


def _classify_error(error: Exception) -> str:
    """Classify error type for logging."""
    error_str = str(error).lower()
    for error_type, patterns in RETRYABLE_ERRORS.items():
        for pattern in patterns:
            if pattern in error_str:
                return error_type
    return "unknown"


# ---------------------------------------------------------------------------
# Profile loader
# ---------------------------------------------------------------------------

def load_campaign_profile(profile_name: str) -> CampaignProfile:
    """Load a campaign profile from YAML config."""
    import yaml
    profile_path = os.path.join("config", "campaign_profiles", f"{profile_name}.yaml")
    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"Campaign profile not found: {profile_path}")

    with open(profile_path) as f:
        data = yaml.safe_load(f)

    profile = CampaignProfile(
        profile_name=data.get("profile_name", profile_name),
        description=data.get("description", ""),
        profile_type=data.get("profile_type", "pilot"),
        domain=data.get("domain", "clean-energy"),
        program_name=data.get("program_name", "clean_energy"),
        mode=data.get("mode", "production"),
        wall_clock_budget_minutes=data.get("wall_clock_budget_minutes", 30),
        candidate_trial_budget=data.get("candidate_trial_budget", 5),
        policy_trial_budget=data.get("policy_trial_budget", 3),
        diagnostic_rich=data.get("diagnostic_rich", True),
        verbose_logging=data.get("verbose_logging", True),
    )

    # Stage overrides
    s1 = data.get("stage1", {})
    profile.stage1_max_trials = s1.get("max_trials", 3)
    profile.stage1_min_score = s1.get("min_score_to_advance", 0.40)
    profile.stage1_wall_clock = s1.get("max_wall_clock_seconds", 600)
    profile.stage1_abandon_floor = s1.get("abandon_floor", 0.30)
    profile.stage1_early_stop_margin = s1.get("early_stop_margin", 0.15)

    profile.stage2_shortlist_size = data.get("stage2_shortlist_size", 3)

    s3 = data.get("stage3", {})
    profile.stage3_max_trials = s3.get("max_trials", 3)
    profile.stage3_min_score = s3.get("min_score_to_advance", 0.50)
    profile.stage3_wall_clock = s3.get("max_wall_clock_seconds", 180)
    profile.stage3_abandon_floor = s3.get("abandon_floor", 0.40)

    profile.stage4_review_prep = data.get("stage4_review_prep", True)

    fals = data.get("falsification", {})
    profile.falsification_enabled = fals.get("enabled", True)
    profile.falsification_strict = fals.get("strict_mode", False)

    # FIX (7D): load falsify_all_finalists from YAML (evaluation profile sets this True)
    profile.falsify_all_finalists = data.get("falsify_all_finalists", False)

    profile.review_packet_generation = data.get("review_packet_generation", True)
    profile.export_artifacts = data.get("export_artifacts", True)

    retry = data.get("retry", {})
    profile.max_retries_per_stage = retry.get("max_retries_per_stage", 2)
    profile.retry_delay_seconds = retry.get("retry_delay_seconds", 5)

    health = data.get("health", {})
    profile.health_min_candidates = health.get("min_candidates_generated", 3)
    profile.health_min_stages = health.get("min_stages_completed", 3)
    profile.health_max_stage_failure_rate = health.get("max_stage_failure_rate", 0.5)
    profile.health_max_retry_count = health.get("max_retry_count", 3)

    return profile


# ---------------------------------------------------------------------------
# Campaign Manager
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CampaignManager:
    """Autonomous campaign manager for pilot and overnight runs.

    Wraps the existing DailySearchLadder with:
    - Preflight verification
    - Lock protection
    - Retry/watchdog behavior
    - Durable state and receipts
    - Artifact export
    """

    def __init__(
        self,
        repo: Optional[Repository] = None,
        db_path: Optional[str] = None,
        lock_dir: Optional[str] = None,
    ):
        self.repo = repo
        self.db_path = db_path
        self.lock = CampaignLock(lock_dir)
        self._shutdown_requested = False

    def run_campaign(
        self,
        profile: CampaignProfile,
        strict_preflight: bool = True,
        dry_run: bool = False,
    ) -> CampaignReceipt:
        """Execute a full campaign with preflight, execution, and export."""
        import os as _os
        campaign_id = new_id()
        # Detect embedding provider from environment
        embed_model = _os.environ.get("BT_EMBEDDING_MODEL", "")
        embedding_provider_name = (
            f"OllamaEmbeddingProvider({embed_model})" if embed_model else "MockEmbeddingProvider"
        )
        receipt = CampaignReceipt(
            campaign_id=campaign_id,
            profile_name=profile.profile_name,
            profile_type=profile.profile_type,
            started_at=_utcnow(),
            config_snapshot=self._profile_to_dict(profile),
            embedding_provider=embedding_provider_name,
        )

        # Setup logging
        if profile.verbose_logging:
            logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

        # ---- Phase 1: Preflight ----
        preflight_event = StageEvent(stage_name="preflight", started_at=_utcnow())
        receipt.status = CampaignStatus.PREFLIGHT.value

        try:
            engine = PreflightEngine()
            preflight_report = engine.run(
                db_path=self.db_path,
                strict=strict_preflight,
                campaign_profile=profile.profile_name,
            )
            receipt.preflight_report = preflight_report.to_dict()
            preflight_event.details = {"readiness_score": preflight_report.readiness_score}

            if strict_preflight and preflight_report.has_failures:
                receipt.status = CampaignStatus.ABORTED_PREFLIGHT.value
                receipt.failure_reason = (
                    f"Preflight failed: {preflight_report.fail_count} critical check(s) failed"
                )
                preflight_event.status = StageStatus.FAILED.value
                preflight_event.error_message = receipt.failure_reason
                preflight_event.completed_at = _utcnow()
                receipt.stage_events.append(preflight_event.to_dict())
                receipt.completed_at = _utcnow()
                self._save_receipt(receipt)
                return receipt

            preflight_event.status = StageStatus.COMPLETED.value
            preflight_event.completed_at = _utcnow()
            receipt.stage_events.append(preflight_event.to_dict())
        except Exception as e:
            receipt.status = CampaignStatus.ABORTED_PREFLIGHT.value
            receipt.failure_reason = f"Preflight error: {e}"
            preflight_event.status = StageStatus.FAILED.value
            preflight_event.error_message = str(e)
            preflight_event.completed_at = _utcnow()
            receipt.stage_events.append(preflight_event.to_dict())
            receipt.completed_at = _utcnow()
            self._save_receipt(receipt)
            return receipt

        if dry_run:
            receipt.status = CampaignStatus.COMPLETED_NO_DRAFT.value
            receipt.failure_reason = "dry_run — execution skipped"
            receipt.completed_at = _utcnow()
            self._save_receipt(receipt)
            return receipt

        # ---- Phase 2: Lock acquisition ----
        lock_event = StageEvent(stage_name="lock_acquisition", started_at=_utcnow())
        if not self.lock.acquire(campaign_id):
            receipt.status = CampaignStatus.ABORTED_RUNTIME.value
            receipt.failure_reason = "Could not acquire campaign lock — another campaign may be running"
            lock_event.status = StageStatus.FAILED.value
            lock_event.error_message = receipt.failure_reason
            lock_event.completed_at = _utcnow()
            receipt.stage_events.append(lock_event.to_dict())
            receipt.completed_at = _utcnow()
            self._save_receipt(receipt)
            return receipt
        lock_event.status = StageStatus.COMPLETED.value
        lock_event.completed_at = _utcnow()
        receipt.stage_events.append(lock_event.to_dict())

        # Install signal handler for clean shutdown
        self._install_signal_handlers()

        try:
            # ---- Phase 3: Initialize DB ----
            init_event = StageEvent(stage_name="db_init", started_at=_utcnow())
            try:
                db = init_db(db_path=self.db_path)
                repo = self.repo or Repository(db)
                self.repo = repo
                init_event.status = StageStatus.COMPLETED.value
            except Exception as e:
                init_event.status = StageStatus.FAILED.value
                init_event.error_message = str(e)
                receipt.status = CampaignStatus.ABORTED_RUNTIME.value
                receipt.failure_reason = f"DB init failed: {e}"
                init_event.completed_at = _utcnow()
                receipt.stage_events.append(init_event.to_dict())
                receipt.completed_at = _utcnow()
                self._save_receipt(receipt)
                return receipt
            init_event.completed_at = _utcnow()
            receipt.stage_events.append(init_event.to_dict())

            # ---- Phase 4: Run daily search ladder ----
            receipt.status = CampaignStatus.RUNNING.value
            self._save_receipt(receipt)  # checkpoint

            campaign_result = self._run_ladder_with_retries(
                repo, profile, receipt
            )

            if self._shutdown_requested:
                receipt.status = CampaignStatus.ABORTED_SIGNAL.value
                receipt.failure_reason = "Shutdown signal received"
            elif campaign_result is None:
                receipt.status = CampaignStatus.ABORTED_RUNTIME.value
                if not receipt.failure_reason:
                    receipt.failure_reason = "Ladder execution failed"
            elif campaign_result.daily_champion_id:
                receipt.status = CampaignStatus.COMPLETED_WITH_DRAFT.value
                receipt.champion_candidate_id = campaign_result.daily_champion_id
                receipt.champion_candidate_title = campaign_result.daily_champion_title or ""
                receipt.total_candidates_generated = campaign_result.total_candidates_generated
                receipt.total_candidates_blocked = campaign_result.total_blocked
                receipt.total_shortlisted = campaign_result.total_shortlisted
                receipt.policy_trials_attempted = campaign_result.policy_trials_attempted
            else:
                receipt.status = CampaignStatus.COMPLETED_NO_DRAFT.value
                receipt.total_candidates_generated = campaign_result.total_candidates_generated if campaign_result else 0

            # ---- Phase 5: Export artifacts ----
            if profile.export_artifacts and campaign_result:
                export_event = StageEvent(stage_name="artifact_export", started_at=_utcnow())
                try:
                    paths = self._export_artifacts(
                        campaign_id, profile, receipt, campaign_result
                    )
                    receipt.artifact_paths = paths
                    export_event.status = StageStatus.COMPLETED.value
                    export_event.details = {"paths": paths}
                except Exception as e:
                    export_event.status = StageStatus.FAILED.value
                    export_event.error_message = str(e)
                    logger.warning("Artifact export failed: %s", e)
                export_event.completed_at = _utcnow()
                receipt.stage_events.append(export_event.to_dict())

            # ---- Phase 6: Health summary ----
            receipt.health_summary = self._compute_health_summary(receipt, profile)

        except Exception as e:
            receipt.status = CampaignStatus.ABORTED_RUNTIME.value
            receipt.failure_reason = f"Unhandled error: {e}"
            logger.error("Campaign aborted: %s", e, exc_info=True)
        finally:
            self.lock.release()
            receipt.completed_at = _utcnow()
            if receipt.started_at:
                try:
                    t0 = datetime.strptime(receipt.started_at, "%Y-%m-%dT%H:%M:%SZ")
                    t1 = datetime.strptime(receipt.completed_at, "%Y-%m-%dT%H:%M:%SZ")
                    receipt.elapsed_seconds = (t1 - t0).total_seconds()
                except Exception:
                    pass
            self._save_receipt(receipt)

        return receipt

    def _run_ladder_with_retries(
        self,
        repo: Repository,
        profile: CampaignProfile,
        receipt: CampaignReceipt,
    ):
        """Run the daily search ladder with retry logic."""
        from .daily_search import DailySearchLadder, LadderConfig, StageConfig

        ladder_event = StageEvent(stage_name="daily_search_ladder", started_at=_utcnow())

        ladder_config = LadderConfig(
            mode="benchmark" if profile.mode == "benchmark" else "production",
            program_name=profile.program_name,
            stage1=StageConfig(
                max_trials=profile.stage1_max_trials,
                min_score_to_advance=profile.stage1_min_score,
                max_wall_clock_seconds=profile.stage1_wall_clock,
                abandon_floor=profile.stage1_abandon_floor,
                early_stop_margin=profile.stage1_early_stop_margin,
            ),
            stage2_shortlist_size=profile.stage2_shortlist_size,
            stage3=StageConfig(
                max_trials=profile.stage3_max_trials,
                min_score_to_advance=profile.stage3_min_score,
                max_wall_clock_seconds=profile.stage3_wall_clock,
                abandon_floor=profile.stage3_abandon_floor,
            ),
            stage4_review_prep=profile.stage4_review_prep,
            # FIX (7D): evaluation profile sets this True for full finalist falsification
            falsify_all_finalists=profile.falsify_all_finalists,
            production_wall_clock_budget_minutes=profile.wall_clock_budget_minutes,
        )

        max_retries = profile.max_retries_per_stage
        retries = 0

        while retries <= max_retries:
            if self._shutdown_requested:
                ladder_event.status = StageStatus.FAILED.value
                ladder_event.error_message = "Shutdown requested"
                ladder_event.completed_at = _utcnow()
                receipt.stage_events.append(ladder_event.to_dict())
                return None

            try:
                # Heartbeat log
                logger.info(
                    "Campaign %s: starting ladder (attempt %d/%d)",
                    receipt.campaign_id[:8], retries + 1, max_retries + 1,
                )

                ladder = DailySearchLadder()
                result = ladder.run_campaign(repo, ladder_config)

                ladder_event.status = StageStatus.COMPLETED.value
                ladder_event.completed_at = _utcnow()
                ladder_event.retries = retries
                ladder_event.details = {
                    "campaign_id": result.campaign_id,
                    "champion_id": result.daily_champion_id,
                    "total_generated": result.total_candidates_generated,
                    "elapsed": round(result.elapsed_seconds, 2),
                    "stages": len(result.ladder_stages),
                }
                receipt.stage_events.append(ladder_event.to_dict())
                receipt.retries_used = retries
                return result

            except Exception as e:
                retries += 1
                receipt.retries_used = retries
                error_type = _classify_error(e)
                logger.warning(
                    "Ladder attempt %d failed (%s): %s",
                    retries, error_type, e,
                )

                if not _is_retryable(e) or retries > max_retries:
                    ladder_event.status = StageStatus.FAILED.value
                    ladder_event.error_message = f"{error_type}: {e}"
                    ladder_event.retries = retries
                    ladder_event.completed_at = _utcnow()
                    receipt.stage_events.append(ladder_event.to_dict())
                    receipt.failure_reason = f"Ladder failed after {retries} attempts: {error_type}: {e}"
                    return None

                # Wait before retry
                time.sleep(profile.retry_delay_seconds)

        return None

    def _export_artifacts(
        self,
        campaign_id: str,
        profile: CampaignProfile,
        receipt: CampaignReceipt,
        campaign_result,
    ) -> list:
        """Export campaign artifacts to the filesystem."""
        runtime_root = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
        campaign_dir = os.path.join(runtime_root, "campaigns", campaign_id)
        os.makedirs(campaign_dir, exist_ok=True)

        paths = []

        # 1. Campaign summary JSON
        summary_path = os.path.join(campaign_dir, "campaign_summary.json")
        with open(summary_path, "w") as f:
            json.dump(receipt.to_dict(), f, indent=2)
        paths.append(summary_path)

        # 2. Campaign summary Markdown
        md_path = os.path.join(campaign_dir, "campaign_summary.md")
        with open(md_path, "w") as f:
            f.write(self._format_campaign_markdown(receipt, campaign_result))
        paths.append(md_path)

        # 3. Health report
        health_path = os.path.join(campaign_dir, "health_report.json")
        with open(health_path, "w") as f:
            json.dump(receipt.health_summary, f, indent=2)
        paths.append(health_path)

        # 4. Preflight report
        preflight_path = os.path.join(campaign_dir, "preflight_report.json")
        with open(preflight_path, "w") as f:
            json.dump(receipt.preflight_report, f, indent=2)
        paths.append(preflight_path)

        # 5. Failure report if aborted
        if "aborted" in receipt.status:
            failure_path = os.path.join(campaign_dir, "failure_report.json")
            with open(failure_path, "w") as f:
                json.dump({
                    "campaign_id": campaign_id,
                    "status": receipt.status,
                    "failure_reason": receipt.failure_reason,
                    "stage_events": receipt.stage_events,
                }, f, indent=2)
            paths.append(failure_path)

        return paths

    def _format_campaign_markdown(self, receipt: CampaignReceipt, campaign_result) -> str:
        """Generate Markdown summary of campaign."""
        lines = [
            f"# Campaign Report: {receipt.campaign_id}",
            "",
            f"**Profile**: {receipt.profile_name} ({receipt.profile_type})",
            f"**Status**: {receipt.status}",
            f"**Started**: {receipt.started_at}",
            f"**Completed**: {receipt.completed_at}",
            f"**Elapsed**: {receipt.elapsed_seconds:.1f}s",
            "",
        ]

        if receipt.champion_candidate_id:
            lines.extend([
                "## Champion Candidate",
                f"- ID: {receipt.champion_candidate_id}",
                f"- Title: {receipt.champion_candidate_title}",
                "",
            ])

        lines.extend([
            "## Statistics",
            f"- Candidates generated: {receipt.total_candidates_generated}",
            f"- Candidates blocked: {receipt.total_candidates_blocked}",
            f"- Shortlisted: {receipt.total_shortlisted}",
            f"- Policy trials: {receipt.policy_trials_attempted}",
            f"- Retries used: {receipt.retries_used}",
            "",
        ])

        if receipt.failure_reason:
            lines.extend([
                "## Failure",
                f"- Reason: {receipt.failure_reason}",
                "",
            ])

        lines.extend([
            "## Stage Events",
        ])
        for event in receipt.stage_events:
            status = event.get("status", "unknown")
            name = event.get("stage_name", "unknown")
            lines.append(f"- **{name}**: {status}")
            if event.get("error_message"):
                lines.append(f"  - Error: {event['error_message']}")

        if receipt.health_summary:
            lines.extend([
                "",
                "## Health Summary",
                f"- Healthy: {receipt.health_summary.get('healthy', False)}",
                f"- Overnight ready: {receipt.health_summary.get('overnight_ready', False)}",
            ])
            for issue in receipt.health_summary.get("issues", []):
                lines.append(f"  - {issue}")

        return "\n".join(lines)

    def _compute_health_summary(
        self,
        receipt: CampaignReceipt,
        profile: CampaignProfile,
    ) -> dict:
        """Compute post-campaign health summary."""
        issues = []
        healthy = True

        # Check candidate generation
        if receipt.total_candidates_generated < profile.health_min_candidates:
            issues.append(
                f"Low candidate count: {receipt.total_candidates_generated} "
                f"(min: {profile.health_min_candidates})"
            )
            healthy = False

        # Check stage completions
        completed_stages = sum(
            1 for e in receipt.stage_events
            if e.get("status") == StageStatus.COMPLETED.value
        )
        if completed_stages < profile.health_min_stages:
            issues.append(
                f"Low stage completion: {completed_stages} "
                f"(min: {profile.health_min_stages})"
            )
            healthy = False

        # Check retry rate
        if receipt.retries_used > profile.health_max_retry_count:
            issues.append(
                f"High retry count: {receipt.retries_used} "
                f"(max: {profile.health_max_retry_count})"
            )
            healthy = False

        # Check failure rate
        total_events = len(receipt.stage_events)
        failed_events = sum(
            1 for e in receipt.stage_events
            if e.get("status") == StageStatus.FAILED.value
        )
        if total_events > 0:
            failure_rate = failed_events / total_events
            if failure_rate > profile.health_max_stage_failure_rate:
                issues.append(
                    f"High stage failure rate: {failure_rate:.1%} "
                    f"(max: {profile.health_max_stage_failure_rate:.0%})"
                )
                healthy = False

        # Check campaign outcome
        campaign_succeeded = receipt.status in (
            CampaignStatus.COMPLETED_WITH_DRAFT.value,
            CampaignStatus.COMPLETED_NO_DRAFT.value,
        )

        overnight_ready = (
            healthy
            and campaign_succeeded
            and receipt.retries_used <= 1
        )

        return {
            "healthy": healthy,
            "campaign_succeeded": campaign_succeeded,
            "overnight_ready": overnight_ready,
            "completed_stages": completed_stages,
            "failed_stages": failed_events,
            "total_stages": total_events,
            "retries_used": receipt.retries_used,
            "candidates_generated": receipt.total_candidates_generated,
            "issues": issues,
        }

    def _save_receipt(self, receipt: CampaignReceipt) -> None:
        """Persist campaign receipt to DB."""
        if self.repo is None:
            return
        try:
            self.repo.db.execute(
                """INSERT OR REPLACE INTO bt_campaign_receipts
                   (campaign_id, profile_name, profile_type, status,
                    config_json, preflight_json, stage_events_json,
                    started_at, completed_at, elapsed_seconds,
                    champion_candidate_id, champion_candidate_title,
                    draft_id, failure_reason,
                    total_candidates_generated, total_blocked, total_shortlisted,
                    policy_trials_attempted, retries_used,
                    artifact_paths_json, health_summary_json,
                    embedding_provider)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    receipt.campaign_id,
                    receipt.profile_name,
                    receipt.profile_type,
                    receipt.status,
                    json.dumps(receipt.config_snapshot),
                    json.dumps(receipt.preflight_report),
                    json.dumps(receipt.stage_events),
                    receipt.started_at,
                    receipt.completed_at,
                    receipt.elapsed_seconds,
                    receipt.champion_candidate_id,
                    receipt.champion_candidate_title,
                    receipt.draft_id,
                    receipt.failure_reason,
                    receipt.total_candidates_generated,
                    receipt.total_candidates_blocked,
                    receipt.total_shortlisted,
                    receipt.policy_trials_attempted,
                    receipt.retries_used,
                    json.dumps(receipt.artifact_paths),
                    json.dumps(receipt.health_summary),
                    receipt.embedding_provider,
                ),
            )
            self.repo.db.commit()
        except Exception as e:
            logger.warning("Failed to save campaign receipt: %s", e)

    def _install_signal_handlers(self) -> None:
        """Install signal handlers for clean shutdown."""
        def _handler(signum, frame):
            logger.warning("Received signal %d — requesting clean shutdown", signum)
            self._shutdown_requested = True

        try:
            signal.signal(signal.SIGTERM, _handler)
            signal.signal(signal.SIGINT, _handler)
        except (OSError, ValueError):
            # Cannot set signal handlers (e.g., not in main thread)
            pass

    def _profile_to_dict(self, profile: CampaignProfile) -> dict:
        """Serialize profile to dict for storage."""
        import os as _os
        embed_model = _os.environ.get("BT_EMBEDDING_MODEL", "")
        return {
            "profile_name": profile.profile_name,
            "profile_type": profile.profile_type,
            "domain": profile.domain,
            "program_name": profile.program_name,
            "mode": profile.mode,
            "wall_clock_budget_minutes": profile.wall_clock_budget_minutes,
            "candidate_trial_budget": profile.candidate_trial_budget,
            "stage1_max_trials": profile.stage1_max_trials,
            "stage2_shortlist_size": profile.stage2_shortlist_size,
            "stage3_max_trials": profile.stage3_max_trials,
            "max_retries_per_stage": profile.max_retries_per_stage,
            "embedding_provider": (
                f"OllamaEmbeddingProvider({embed_model})" if embed_model else "MockEmbeddingProvider"
            ),
            "embedding_model": embed_model or "mock",
        }

    def get_receipt(self, campaign_id: str) -> Optional[dict]:
        """Load a campaign receipt from DB."""
        if self.repo is None:
            return None
        try:
            row = self.repo.db.execute(
                "SELECT * FROM bt_campaign_receipts WHERE campaign_id=?",
                (campaign_id,),
            ).fetchone()
            if row:
                return dict(row)
            return None
        except Exception:
            return None

    def list_campaigns(self, limit: int = 20) -> list:
        """List recent campaign receipts."""
        if self.repo is None:
            return []
        try:
            rows = self.repo.db.execute(
                "SELECT campaign_id, profile_name, status, started_at, completed_at "
                "FROM bt_campaign_receipts ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
