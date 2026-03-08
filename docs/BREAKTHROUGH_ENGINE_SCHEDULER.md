# Breakthrough Engine - Scheduler Guide

## Overview

The scheduler provides safe daily execution with overlap protection, structured exit states, and report emission.

## Quick Start

### Run Once (Manual)
```bash
python -m breakthrough_engine schedule run-once --program general_fast_loop
```

### Set Up Daily Automation (macOS)

1. Generate the launchd plist:
```bash
python -m breakthrough_engine schedule generate-plist --program general_fast_loop --hour 6 > ~/Library/LaunchAgents/com.scires.breakthrough.plist
```

2. Load it:
```bash
launchctl load ~/Library/LaunchAgents/com.scires.breakthrough.plist
```

3. Verify:
```bash
launchctl list | grep scires.breakthrough
```

### Cron Fallback (Linux/Generic)
```bash
# Add to crontab -e:
0 6 * * * cd /path/to/repo && /path/to/venv/bin/python -m breakthrough_engine schedule run-once --program general_fast_loop >> runtime/logs/breakthrough-cron.log 2>&1
```

## Overlap Protection

The scheduler uses a lock file at `runtime/state/breakthrough.lock`. If a run is already active:
- New runs are **blocked** (not queued)
- Exit status: `skipped_due_to_active_lock`
- Stale locks (>2 hours old) are automatically removed

## Exit States

| Status | Meaning |
|--------|---------|
| `success` | Run completed, one candidate published |
| `completed_no_publication` | Run completed, no candidate met threshold |
| `failed` | Error during execution |
| `skipped_due_to_active_lock` | Another run is active |

## Artifacts

Each scheduled run produces:
- `runtime/breakthrough_reports/scheduled_YYYYMMDD_HHMMSS.json` — run metadata
- `runtime/breakthrough_reports/run_<ID>.json` — full JSON report
- `runtime/breakthrough_reports/run_<ID>.md` — Markdown report

## Configuration

Environment variables:
- `SCIRES_RUNTIME_ROOT` — base directory for all runtime data (default: `runtime/`)
- `SCIRES_REPO_ROOT` — repo root for config lookup

## Cleanup

Old artifacts can be cleaned up:
```python
from breakthrough_engine.scheduler import cleanup_old_artifacts
removed = cleanup_old_artifacts(max_age_days=30)
```

## Troubleshooting

**Lock file stuck**: Check `runtime/state/breakthrough.lock`. If the PID listed is not running, delete the file manually.

**Scheduled run not firing**: Check launchd logs:
```bash
cat runtime/logs/breakthrough-scheduled.log
cat runtime/logs/breakthrough-scheduled-err.log
```

**Permission errors**: Ensure the Python venv and runtime directories are accessible to the user running launchd.
