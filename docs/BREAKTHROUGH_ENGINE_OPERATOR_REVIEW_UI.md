# Breakthrough Engine - Operator Review UI (Phase 4B)

## Overview

Phase 4B adds a minimal read-only HTML review interface at `/api/breakthrough/view/review`. This supplements the existing CLI and JSON API review workflows.

## Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/breakthrough/view/review` | GET | HTML review queue with trust signals |
| `/api/breakthrough/view/candidate/<id>` | GET | JSON candidate detail with all signals |
| `/api/breakthrough/view/latest` | GET | Latest publication (existing) |
| `/api/breakthrough/view/runs` | GET | Recent runs (existing, now links to review) |

## Review Queue View

The review queue shows each pending draft with:

### Draft Summary
- Title, draft ID, run ID, replication priority
- Hypothesis text
- Evidence summary

### Trust Signals Table
- Novelty decision and score
- Embedding similarity (max) and basis
- Domain-fit score and matched keywords

### Gate Diagnostics
- Per-gate pass/fail with scores and reasons
- Shows novelty, domain_fit, and publication gates

### Score Breakdown
- All scoring dimensions with values

### Actions
- Approve / Reject buttons (POST to existing API endpoints)

## Design Principles

1. **Minimal**: No SPA, no JavaScript framework, no build step
2. **Read-only** except for approve/reject actions
3. **Lightweight CSS**: System fonts, max-width container, simple table styling
4. **Preserves existing flows**: CLI and JSON API remain primary interfaces
5. **Trust-focused**: Shows the signals an operator needs to make a decision

## Candidate Detail API

`GET /api/breakthrough/view/candidate/<id>` returns JSON with:
- `candidate`: full candidate record
- `score`: scoring breakdown
- `novelty`: lexical novelty check
- `domain_fit`: domain relevance assessment
- `embedding_novelty`: semantic similarity details
- `evidence_rankings`: ranked evidence with explanations
