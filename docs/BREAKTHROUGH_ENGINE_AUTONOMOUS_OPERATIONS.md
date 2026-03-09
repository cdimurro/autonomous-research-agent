# Autonomous Operations Guide

## Overview

Phase 7A introduces autonomous campaign execution with durable state,
preflight verification, retry logic, and structured artifact export.

## Architecture

```
User → CLI → CampaignManager → PreflightEngine → DailySearchLadder → DB
                    ↓                                       ↓
               CampaignLock                          ArtifactExport
                    ↓                                       ↓
            CampaignReceipt (DB)                   runtime/campaigns/
```

## Campaign Lifecycle

1. **Preflight** — 15 environment checks with PASS/WARN/FAIL
2. **Lock acquisition** — File-based lock with PID-alive check
3. **DB init** — Apply any pending migrations
4. **Ladder execution** — DailySearchLadder with retry logic
5. **Artifact export** — JSON, Markdown, health report
6. **Health summary** — Post-campaign health assessment
7. **Receipt persistence** — Durable record in `bt_campaign_receipts`

## Retry Behavior

Retryable errors:
- Ollama timeouts
- SQLite database locks
- File write permission errors

Non-retryable errors are classified as `unknown` and cause immediate abort.

Max retries per profile:
- Pilot: 2 retries, 5s delay
- Overnight: 3 retries, 10s delay

## Lock Protection

Campaign lock prevents overlapping autonomous campaigns:
- Lock file: `runtime/campaign.lock`
- Contains: campaign_id, PID, timestamp
- Stale lock detection: checks if PID is alive
- Automatic cleanup on campaign completion

## Signal Handling

SIGTERM and SIGINT trigger clean shutdown:
- Current stage completes
- Receipt is checkpointed to DB
- Lock is released
- Status set to `aborted_signal`

## Health Assessment

Post-campaign health checks:
- Minimum candidates generated
- Minimum stages completed
- Stage failure rate below threshold
- Retry count within bounds
- Campaign succeeded (no abort)

`overnight_ready` requires:
- All health checks pass
- Campaign completed (with or without draft)
- 0-1 retries used
