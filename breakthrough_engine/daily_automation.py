"""Bounded daily automation for the Breakthrough Engine Phase 8.

Manages one evaluation campaign/day and one production campaign/day.
Every run is bounded, logged, and feeds the review queue.

Key design decisions:
- Max 1 run per profile per calendar day (enforced by bt_daily_automation_runs)
- Dry-run mode never writes to the campaign database
- All outcomes are logged with policy ID and timestamp
- Review queue insertion is automatic for drafts
- No unattended perpetual operation by default
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Daily automation outcome strings
OUTCOME_COMPLETED_WITH_DRAFT = "completed_with_draft"
OUTCOME_COMPLETED_NO_DRAFT = "completed_no_draft"
OUTCOME_ABORTED_PREFLIGHT = "aborted_preflight"
OUTCOME_ABORTED_RUNTIME = "aborted_runtime"
OUTCOME_DRY_RUN = "dry_run"
OUTCOME_ALREADY_RAN_TODAY = "already_ran_today"

VALID_OUTCOMES = {
    OUTCOME_COMPLETED_WITH_DRAFT,
    OUTCOME_COMPLETED_NO_DRAFT,
    OUTCOME_ABORTED_PREFLIGHT,
    OUTCOME_ABORTED_RUNTIME,
    OUTCOME_DRY_RUN,
    OUTCOME_ALREADY_RAN_TODAY,
}

DAILY_PROFILES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "daily_profiles",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DailyAutomationProfile:
    """Configuration for a bounded daily automation profile."""
    profile_name: str
    profile_type: str               # "evaluation_daily" | "production_daily"
    campaign_profile: str           # campaign profile name (e.g. eval_clean_energy_30m)
    domain: str = "clean-energy"
    max_runs_per_day: int = 1
    dry_run_default: bool = False
    require_integrity_ok: bool = False
    require_falsification_complete: bool = False
    export_evaluation_pack: bool = False
    insert_review_queue: bool = True
    review_labels_required: dict = field(default_factory=dict)
    review_queue_on_draft: bool = True
    log_posterior_snapshot: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "profile_name": self.profile_name,
            "profile_type": self.profile_type,
            "campaign_profile": self.campaign_profile,
            "domain": self.domain,
            "max_runs_per_day": self.max_runs_per_day,
            "dry_run_default": self.dry_run_default,
            "require_integrity_ok": self.require_integrity_ok,
            "require_falsification_complete": self.require_falsification_complete,
            "export_evaluation_pack": self.export_evaluation_pack,
            "insert_review_queue": self.insert_review_queue,
            "review_labels_required": self.review_labels_required,
            "review_queue_on_draft": self.review_queue_on_draft,
            "log_posterior_snapshot": self.log_posterior_snapshot,
            "description": self.description,
        }


@dataclass
class DailyRunResult:
    """Result of a single daily automation run."""
    run_id: str = ""
    profile_name: str = ""
    campaign_id: str = ""
    policy_id: str = ""
    outcome: str = "unknown"
    dry_run: bool = False
    error_message: str = ""
    started_at: str = ""
    completed_at: str = ""
    run_date: str = ""
    review_queue_item_id: str = ""
    operator_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "profile_name": self.profile_name,
            "campaign_id": self.campaign_id,
            "policy_id": self.policy_id,
            "outcome": self.outcome,
            "dry_run": self.dry_run,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "run_date": self.run_date,
            "review_queue_item_id": self.review_queue_item_id,
            "operator_summary": self.operator_summary,
        }


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------

def load_daily_profile(profile_name: str, profiles_dir: Optional[str] = None) -> DailyAutomationProfile:
    """Load a daily automation profile from YAML config.

    Args:
        profile_name: Profile name (e.g. "evaluation_daily_clean_energy")
        profiles_dir: Override directory for profiles

    Returns:
        DailyAutomationProfile

    Raises:
        FileNotFoundError: If the profile config file doesn't exist
        ValueError: If the profile config is invalid
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required: pip install pyyaml")

    d = profiles_dir or DAILY_PROFILES_DIR
    path = os.path.join(d, f"{profile_name}.yaml")

    if not os.path.exists(path):
        raise FileNotFoundError(f"Daily profile not found: {path}")

    with open(path) as f:
        config = yaml.safe_load(f)

    if not config:
        raise ValueError(f"Empty daily profile config: {path}")

    return DailyAutomationProfile(
        profile_name=config.get("profile_name", profile_name),
        profile_type=config.get("profile_type", "evaluation_daily"),
        campaign_profile=config.get("campaign_profile", "eval_clean_energy_30m"),
        domain=config.get("domain", "clean-energy"),
        max_runs_per_day=config.get("max_runs_per_day", 1),
        dry_run_default=config.get("dry_run_default", False),
        require_integrity_ok=config.get("require_integrity_ok", False),
        require_falsification_complete=config.get("require_falsification_complete", False),
        export_evaluation_pack=config.get("export_evaluation_pack", False),
        insert_review_queue=config.get("insert_review_queue", True),
        review_labels_required=config.get("review_labels_required", {}),
        review_queue_on_draft=config.get("review_queue_on_draft", True),
        log_posterior_snapshot=config.get("log_posterior_snapshot", False),
        description=config.get("description", "").strip(),
    )


def list_available_profiles(profiles_dir: Optional[str] = None) -> list[str]:
    """Return names of all available daily automation profiles."""
    d = profiles_dir or DAILY_PROFILES_DIR
    if not os.path.exists(d):
        return []
    return [
        f[:-5]  # strip .yaml
        for f in os.listdir(d)
        if f.endswith(".yaml")
    ]


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

def dry_run_profile(
    profile: DailyAutomationProfile,
    repo,
    run_date: Optional[str] = None,
) -> DailyRunResult:
    """Perform a dry run — describe what would happen without executing.

    Returns a DailyRunResult with outcome=OUTCOME_DRY_RUN and a detailed
    operator_summary explaining what would happen.
    """
    from .models import new_id
    today = run_date or _today()

    # Check if already ran today
    already_ran = repo.has_daily_run_today(profile.profile_name, today)

    # Get current champion policy
    champion_policy_id = "phase5_champion"
    try:
        from .policy_registry import PolicyRegistry
        reg = PolicyRegistry(repo)
        champ = reg.get_champion()
        champion_policy_id = champ.id
    except Exception as e:
        logger.debug("Could not get champion policy: %s", e)

    summary_lines = [
        f"DRY RUN: {profile.profile_name}",
        f"=========================================",
        f"Date: {today}",
        f"Campaign profile: {profile.campaign_profile}",
        f"Domain: {profile.domain}",
        f"Max runs per day: {profile.max_runs_per_day}",
        f"Already ran today: {already_ran}",
        f"Champion policy: {champion_policy_id}",
        f"Requires integrity_ok: {profile.require_integrity_ok}",
        f"Exports evaluation pack: {profile.export_evaluation_pack}",
        f"Inserts review queue: {profile.insert_review_queue}",
        f"",
        f"What would happen:",
    ]

    if already_ran:
        summary_lines.append(f"  → SKIP: profile '{profile.profile_name}' already ran today ({today})")
    else:
        summary_lines.append(f"  → Would run campaign with profile '{profile.campaign_profile}'")
        summary_lines.append(f"  → Would use policy: {champion_policy_id}")
        if profile.export_evaluation_pack:
            summary_lines.append(f"  → Would export evaluation pack (schema v003)")
        if profile.insert_review_queue:
            summary_lines.append(f"  → If draft found: would insert into review queue")
        summary_lines.append(f"  → Would log run to bt_daily_automation_runs")

    run_id = new_id()
    result = DailyRunResult(
        run_id=run_id,
        profile_name=profile.profile_name,
        campaign_id="",
        policy_id=champion_policy_id,
        outcome=OUTCOME_DRY_RUN,
        dry_run=True,
        started_at=_utcnow(),
        completed_at=_utcnow(),
        run_date=today,
        operator_summary="\n".join(summary_lines),
    )

    # Log the dry run record
    try:
        repo.insert_daily_run({
            "id": run_id,
            "profile_name": profile.profile_name,
            "campaign_id": "",
            "policy_id": champion_policy_id,
            "outcome": OUTCOME_DRY_RUN,
            "dry_run": True,
            "error_message": "",
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "run_date": today,
        })
    except Exception as e:
        logger.debug("Could not log dry run: %s", e)

    return result


# ---------------------------------------------------------------------------
# Review queue insertion
# ---------------------------------------------------------------------------

def build_review_queue_item(
    daily_run_id: str,
    profile: DailyAutomationProfile,
    campaign_result: dict,
    policy_id: str = "",
) -> dict:
    """Build a review queue item dict from a campaign result.

    Args:
        daily_run_id: ID of the daily automation run
        profile: The daily profile that produced this run
        campaign_result: Campaign result dict (from campaign receipt / daily search)
        policy_id: Policy used for this campaign

    Returns:
        Review queue item dict ready to insert via repo.insert_review_queue_item()
    """
    champion = campaign_result.get("champion", {})
    champion_title = champion.get("title", campaign_result.get("champion_title", ""))
    champion_score = champion.get("final_score", campaign_result.get("champion_score", 0.0))
    champion_candidate_id = champion.get("id", campaign_result.get("champion_candidate_id", ""))
    campaign_id = campaign_result.get("campaign_id", "")

    # Falsification summary
    falsif_summary = champion.get("falsification_risk", "unknown")
    if isinstance(champion.get("falsification_result"), dict):
        falsif_summary = champion["falsification_result"].get("summary", falsif_summary)

    # Rationale
    rationale = campaign_result.get("champion_rationale", "")
    if not rationale:
        rationale = f"Champion selected from {campaign_result.get('finalist_count', '?')} finalists with score {champion_score:.3f}"

    # Outcome
    has_draft = bool(campaign_result.get("has_draft", False))
    outcome = OUTCOME_COMPLETED_WITH_DRAFT if has_draft else OUTCOME_COMPLETED_NO_DRAFT

    return {
        "campaign_id": campaign_id,
        "daily_run_id": daily_run_id,
        "profile_name": profile.profile_name,
        "policy_id": policy_id,
        "champion_title": champion_title,
        "champion_score": champion_score,
        "champion_candidate_id": champion_candidate_id,
        "falsification_summary": falsif_summary,
        "rationale": rationale,
        "outcome": outcome,
        "review_status": "pending",
    }


def format_operator_summary(result: DailyRunResult, profile: DailyAutomationProfile) -> str:
    """Format a concise operator summary for a daily run result."""
    lines = [
        f"Daily Run Summary — {profile.profile_name}",
        f"==========================================",
        f"Date: {result.run_date}",
        f"Outcome: {result.outcome.upper()}",
        f"Campaign ID: {result.campaign_id or '(none)'}",
        f"Policy used: {result.policy_id or '(unknown)'}",
        f"Run ID: {result.run_id}",
    ]

    if result.error_message:
        lines.append(f"Error: {result.error_message}")

    if result.review_queue_item_id:
        lines.append(f"Review queue item: {result.review_queue_item_id}")
        lines.append(f"  → Check with: python -m breakthrough_engine review-queue inspect {result.review_queue_item_id}")

    if result.outcome == OUTCOME_COMPLETED_WITH_DRAFT:
        lines.append(f"  → A review-worthy draft was produced. Please add review labels.")
    elif result.outcome == OUTCOME_COMPLETED_NO_DRAFT:
        lines.append(f"  → No draft above threshold. No action required.")
    elif result.outcome == OUTCOME_ABORTED_PREFLIGHT:
        lines.append(f"  → Campaign aborted at preflight. Check preflight logs.")
    elif result.outcome == OUTCOME_ABORTED_RUNTIME:
        lines.append(f"  → Campaign aborted at runtime. Check error message above.")
    elif result.outcome == OUTCOME_DRY_RUN:
        lines.append(f"  → Dry run only. No campaign was executed.")
    elif result.outcome == OUTCOME_ALREADY_RAN_TODAY:
        lines.append(f"  → Profile already ran today. Skipped.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Daily status check
# ---------------------------------------------------------------------------

def get_daily_status(repo, run_date: Optional[str] = None) -> dict:
    """Get the status of all daily automation runs for a given date.

    Returns a dict with profile_name → last run info.
    """
    today = run_date or _today()
    profiles = list_available_profiles()
    status = {}

    for profile_name in profiles:
        try:
            runs = repo.list_daily_runs(run_date=today, profile_name=profile_name)
            real_runs = [r for r in runs if not r.get("dry_run")]
            status[profile_name] = {
                "ran_today": len(real_runs) > 0,
                "run_count": len(real_runs),
                "last_outcome": real_runs[0]["outcome"] if real_runs else None,
                "last_campaign_id": real_runs[0].get("campaign_id", "") if real_runs else None,
            }
        except Exception as e:
            status[profile_name] = {"error": str(e)}

    return {"date": today, "profiles": status}
