# Overnight Campaign Runbook

## Prerequisites

1. Pilot campaign must have completed successfully
2. System health check must show "overnight_ready: True"
3. Ollama server must be running with the target model loaded
4. Sufficient disk space (5GB+ recommended)

## Pre-Launch Checklist

```bash
# 1. Verify system readiness
python -m breakthrough_engine preflight --strict --profile overnight_clean_energy

# 2. Verify pilot results (if not already done)
python -m breakthrough_engine campaign list

# 3. Check Ollama is healthy
curl -s http://127.0.0.1:11434/api/tags | python -m json.tool

# 4. Check disk space
df -h runtime/
```

## Launch Command

```bash
# Standard overnight launch (recommended)
python -m breakthrough_engine campaign run --profile overnight_clean_energy

# With custom DB path
python -m breakthrough_engine campaign run --profile overnight_clean_energy --db /path/to/scires.db

# Dry-run (preflight only, no execution)
python -m breakthrough_engine campaign run --profile overnight_clean_energy --dry-run
```

## Expected Behavior

- **Duration**: Up to 8 hours (480 minutes wall-clock budget)
- **Domain**: clean-energy only
- **Mode**: Quality-first production search
- **Sub-domains**: electrocatalysts, photovoltaics, battery-materials, hydrogen-storage, thermoelectrics
- **Output**: Campaign artifacts in `runtime/campaigns/<campaign_id>/`

## During Execution

The campaign manager handles:
- Automatic retries for transient Ollama timeouts and DB locks
- Clean shutdown on SIGTERM/SIGINT
- Periodic checkpointing to DB
- Lock protection against overlapping campaigns

## Morning-After Inspection

```bash
# 1. Check campaign status
python -m breakthrough_engine campaign list

# 2. View campaign details
python -m breakthrough_engine campaign show <CAMPAIGN_ID>

# 3. Check artifacts
ls -la runtime/campaigns/<CAMPAIGN_ID>/

# 4. Read campaign summary
cat runtime/campaigns/<CAMPAIGN_ID>/campaign_summary.md

# 5. Check health report
cat runtime/campaigns/<CAMPAIGN_ID>/health_report.json | python -m json.tool

# 6. If a champion was produced, review it
python -m breakthrough_engine cockpit show <RUN_ID>
```

## Inspecting the Database

```bash
# Open SQLite
sqlite3 runtime/db/scires.db

# Recent campaigns
SELECT campaign_id, profile_name, status, started_at, completed_at
FROM bt_campaign_receipts ORDER BY started_at DESC LIMIT 5;

# Campaign details
SELECT * FROM bt_campaign_receipts WHERE campaign_id = '<ID>';

# Stage events for a campaign
SELECT * FROM bt_campaign_heartbeats WHERE campaign_id = '<ID>';

# Daily search results
SELECT * FROM bt_daily_campaigns ORDER BY started_at DESC LIMIT 5;
```

## Recovery from Failure

### Campaign lock stuck
```bash
# Check if lock exists
ls -la runtime/campaign.lock

# If no campaign is running, remove it
rm runtime/campaign.lock
```

### Campaign aborted mid-run
```bash
# Check the failure report
cat runtime/campaigns/<CAMPAIGN_ID>/failure_report.json | python -m json.tool

# The campaign receipt in DB will show the abort reason
python -m breakthrough_engine campaign show <CAMPAIGN_ID>

# Re-launch (will create a new campaign)
python -m breakthrough_engine campaign run --profile overnight_clean_energy
```

### Ollama crashed during run
```bash
# Restart Ollama
ollama serve &

# Wait a few seconds, then re-launch
python -m breakthrough_engine campaign run --profile overnight_clean_energy
```

## Campaign Outcome Categories

| Status | Meaning |
|--------|---------|
| `completed_with_draft` | Success — a champion candidate was produced |
| `completed_no_draft` | Pipeline ran but no candidate met quality threshold |
| `aborted_preflight` | Pre-launch checks failed |
| `aborted_runtime` | Execution failed (see failure_reason) |
| `aborted_timeout` | Wall-clock budget exceeded |
| `aborted_signal` | Clean shutdown via SIGTERM/SIGINT |

## Overnight Profile Settings

| Setting | Value |
|---------|-------|
| Wall-clock budget | 480 min (8 hours) |
| Stage 1 trials | 10 |
| Stage 1 wall clock | 3600s |
| Stage 2 shortlist | 5 |
| Stage 3 trials | 5 |
| Max retries/stage | 3 |
| Falsification | strict |
| Publication threshold | 0.70 |
