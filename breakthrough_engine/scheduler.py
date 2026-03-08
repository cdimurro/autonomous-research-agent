"""Scheduler hardening for daily breakthrough runs.

Provides:
- Lock-file based overlap protection
- Structured exit states
- Timestamped report/artifact emission
- Configurable schedule settings
- Run retention / cleanup
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from .config_loader import load_program, validate_program
from .db import Repository, init_db
from .orchestrator import BreakthroughOrchestrator
from .reporting import save_reports

logger = logging.getLogger(__name__)


class ScheduledRunStatus(str, Enum):
    SUCCESS = "success"
    COMPLETED_NO_PUBLICATION = "completed_no_publication"
    FAILED = "failed"
    SKIPPED_DUE_TO_ACTIVE_LOCK = "skipped_due_to_active_lock"


# ---------------------------------------------------------------------------
# Lock file management
# ---------------------------------------------------------------------------

class RunLock:
    """File-based lock to prevent overlapping runs."""

    def __init__(self, lock_dir: Optional[str] = None):
        root = lock_dir or os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
        self.lock_path = Path(root) / "state" / "breakthrough.lock"
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns False if already held."""
        if self.lock_path.exists():
            # Check if the lock is stale (older than 2 hours)
            try:
                with open(self.lock_path) as f:
                    lock_data = json.load(f)
                lock_time = datetime.fromisoformat(lock_data.get("started_at", ""))
                age_hours = (datetime.now(timezone.utc) - lock_time.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                if age_hours > 2.0:
                    logger.warning("Stale lock detected (%.1f hours old), removing", age_hours)
                    self.release()
                else:
                    logger.info("Active lock found (pid=%s, started=%s)",
                                lock_data.get("pid"), lock_data.get("started_at"))
                    return False
            except (json.JSONDecodeError, ValueError, OSError):
                logger.warning("Corrupt lock file, removing")
                self.release()

        lock_data = {
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "hostname": os.uname().nodename,
        }
        try:
            with open(self.lock_path, "x") as f:
                json.dump(lock_data, f)
            return True
        except FileExistsError:
            return False

    def release(self):
        """Release the lock."""
        try:
            self.lock_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Failed to release lock: %s", e)

    def is_locked(self) -> bool:
        return self.lock_path.exists()

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Could not acquire run lock")
        return self

    def __exit__(self, *args):
        self.release()


# ---------------------------------------------------------------------------
# Scheduled run execution
# ---------------------------------------------------------------------------

def run_scheduled(
    program_name: str = "general_fast_loop",
    db_path: Optional[str] = None,
    lock_dir: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> tuple[ScheduledRunStatus, str]:
    """Execute a single scheduled breakthrough run with overlap protection.

    Returns (status, message).
    """
    lock = RunLock(lock_dir=lock_dir)

    if not lock.acquire():
        msg = "Skipped: another run is active (lock held)"
        logger.info(msg)
        _emit_run_artifact(
            ScheduledRunStatus.SKIPPED_DUE_TO_ACTIVE_LOCK,
            msg, output_dir=output_dir,
        )
        return ScheduledRunStatus.SKIPPED_DUE_TO_ACTIVE_LOCK, msg

    try:
        # Load and validate program
        try:
            program = load_program(program_name)
        except FileNotFoundError as e:
            msg = f"Program not found: {e}"
            logger.error(msg)
            _emit_run_artifact(ScheduledRunStatus.FAILED, msg, output_dir=output_dir)
            return ScheduledRunStatus.FAILED, msg

        errors = validate_program(program)
        if errors:
            msg = f"Config validation errors: {errors}"
            logger.error(msg)
            _emit_run_artifact(ScheduledRunStatus.FAILED, msg, output_dir=output_dir)
            return ScheduledRunStatus.FAILED, msg

        # Initialize DB and run
        db = init_db(db_path=db_path)
        repo = Repository(db)

        orchestrator = BreakthroughOrchestrator(program=program, repo=repo)
        run_record = orchestrator.run()

        # Save reports
        report_dir = output_dir or os.path.join(
            os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"),
            "breakthrough_reports",
        )
        json_path, md_path = save_reports(repo, run_record.id, output_dir=report_dir)

        # Determine status
        if run_record.publication_id:
            status = ScheduledRunStatus.SUCCESS
            pub = repo.get_publication(run_record.publication_id)
            pub_title = pub.get("candidate_title", "unknown") if pub else "unknown"
            msg = f"Published: {pub_title} (run={run_record.id})"
        else:
            status = ScheduledRunStatus.COMPLETED_NO_PUBLICATION
            msg = f"No publication (run={run_record.id})"

        _emit_run_artifact(
            status, msg,
            run_id=run_record.id,
            json_report=json_path,
            md_report=md_path,
            output_dir=output_dir,
        )

        logger.info("Scheduled run completed: %s - %s", status.value, msg)
        return status, msg

    except Exception as e:
        msg = f"Run failed with error: {e}"
        logger.error(msg, exc_info=True)
        _emit_run_artifact(ScheduledRunStatus.FAILED, msg, output_dir=output_dir)
        return ScheduledRunStatus.FAILED, msg

    finally:
        lock.release()


def _emit_run_artifact(
    status: ScheduledRunStatus,
    message: str,
    run_id: str = "",
    json_report: str = "",
    md_report: str = "",
    output_dir: Optional[str] = None,
):
    """Write a timestamped run artifact for the scheduled run."""
    root = output_dir or os.path.join(
        os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"),
        "breakthrough_reports",
    )
    d = Path(root)
    d.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    artifact = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status.value,
        "message": message,
        "run_id": run_id,
        "json_report": json_report,
        "md_report": md_report,
    }

    path = d / f"scheduled_{ts}.json"
    with open(path, "w") as f:
        json.dump(artifact, f, indent=2)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup_old_artifacts(
    max_age_days: int = 30,
    output_dir: Optional[str] = None,
):
    """Remove run artifacts older than max_age_days."""
    root = output_dir or os.path.join(
        os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"),
        "breakthrough_reports",
    )
    d = Path(root)
    if not d.exists():
        return 0

    cutoff = time.time() - (max_age_days * 86400)
    removed = 0
    for f in d.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1

    if removed:
        logger.info("Cleaned up %d old artifacts (>%d days)", removed, max_age_days)
    return removed


# ---------------------------------------------------------------------------
# launchd plist template
# ---------------------------------------------------------------------------

LAUNCHD_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.scires.breakthrough</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>breakthrough_engine</string>
        <string>schedule</string>
        <string>run-once</string>
        <string>--program</string>
        <string>{program_name}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{repo_root}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>SCIRES_REPO_ROOT</key>
        <string>{repo_root}</string>
        <key>SCIRES_RUNTIME_ROOT</key>
        <string>{runtime_root}</string>
    </dict>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>{runtime_root}/logs/breakthrough-scheduled.log</string>

    <key>StandardErrorPath</key>
    <string>{runtime_root}/logs/breakthrough-scheduled-err.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def generate_launchd_plist(
    program_name: str = "general_fast_loop",
    hour: int = 6,
    minute: int = 0,
) -> str:
    """Generate a launchd plist for scheduled breakthrough runs."""
    repo_root = os.environ.get(
        "SCIRES_REPO_ROOT",
        str(Path(__file__).resolve().parent.parent),
    )
    runtime_root = os.environ.get("SCIRES_RUNTIME_ROOT", os.path.join(repo_root, "runtime"))
    python_path = sys.executable

    return LAUNCHD_TEMPLATE.format(
        python_path=python_path,
        program_name=program_name,
        repo_root=repo_root,
        runtime_root=runtime_root,
        hour=hour,
        minute=minute,
    )
