# Breakthrough Engine -- Review Workflow

## Overview

In `production_review` mode, the orchestrator creates a `PublicationDraft` instead of auto-publishing a result. This introduces a human review step before any hypothesis becomes a published output, providing a safety layer for production deployments.

## Draft Lifecycle

A publication draft follows a simple two-outcome lifecycle:

```
pending_review  →  approved  →  creates publication
                →  rejected  →  no publication created
```

1. **pending_review** -- The orchestrator produces a scored candidate and wraps it in a `PublicationDraft` rather than immediately creating a publication record.
2. **approved** -- A reviewer approves the draft. The system then creates the corresponding publication, preserving the one-publication-per-run invariant.
3. **rejected** -- A reviewer rejects the draft with a reason. No publication is created for that run.

The one-publication-per-run invariant is preserved regardless of mode: each orchestrator run produces at most one publication (or one draft that may later become a publication).

## Mode Behavior

### Auto-publish modes

The following modes bypass review and publish directly:

- `deterministic_test`
- `demo_local`
- `production_local`
- `omniverse_stub`
- `omniverse_dry_run`

### Review mode

- **`production_review`** -- Creates a `PublicationDraft` for human review. This should be the default for scheduled live runs.

### Shadow mode

- **`production_shadow`** -- Runs the full pipeline but produces neither a publication nor a draft. Used for monitoring and validation without any visible output.

## CLI Commands

The CLI exposes four review subcommands:

| Command                          | Description                                      |
|----------------------------------|--------------------------------------------------|
| `review list`                    | List all drafts in the review queue               |
| `review show <draft_id>`        | Display full details of a specific draft          |
| `review approve <draft_id>`     | Approve a draft, creating its publication         |
| `review reject <draft_id> --reason <text>` | Reject a draft with a required reason  |

## API Routes

The HTTP API provides equivalent functionality:

| Method | Route                         | Description                          |
|--------|-------------------------------|--------------------------------------|
| GET    | `/review/queue`               | List pending drafts                  |
| GET    | `/review/drafts/<id>`         | Retrieve a specific draft            |
| POST   | `/review/drafts/<id>/approve` | Approve a draft                      |
| POST   | `/review/drafts/<id>/reject`  | Reject a draft (body includes reason)|

## Review Events

Every review action is persisted in the `bt_review_events` table with the following fields:

| Field       | Type        | Description                                 |
|-------------|-------------|---------------------------------------------|
| `reviewer`  | `str`       | Identifier of the person taking action      |
| `action`    | `str`       | One of `approve` or `reject`                |
| `notes`     | `str`       | Reason for rejection or approval comments   |
| `timestamp` | `datetime`  | When the action occurred                    |

This provides a complete audit trail of all review decisions.

## Safety Recommendation

`production_review` should be the default mode for any scheduled or automated live runs. Auto-publish modes are appropriate for development, testing, and demos, but production systems benefit from the human-in-the-loop safeguard that the review workflow provides.
