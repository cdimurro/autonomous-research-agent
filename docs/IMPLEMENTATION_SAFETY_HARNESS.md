# Implementation Safety Harness

## Purpose

The Implementation Safety Harness (ISH) is a repo-native workflow that protects the codebase against:

- Authority drift (changes exceeding declared scope)
- Technical drift (wiring/contract breakage)
- Vibe-coding drift (unreviewed implementation)
- Regressions (untested changes reaching main)
- Silent contract breakage
- Docs/workflow divergence

## Workflow Overview

```
┌─────────────────────────────────────────────────────────┐
│  1. INIT SESSION                                        │
│     python scripts/impl_session.py init --scope "..."   │
├─────────────────────────────────────────────────────────┤
│  2. IMPLEMENT                                           │
│     Opus writes code within declared scope              │
├─────────────────────────────────────────────────────────┤
│  3. VERIFY                                              │
│     python scripts/impl_session.py verify               │
│     (runs static checks + targeted tests)               │
├─────────────────────────────────────────────────────────┤
│  4. CODEX REVIEW                                        │
│     GPT-5.2-Codex-mini reviews diff + contracts         │
│     Results written to active_review.json               │
├─────────────────────────────────────────────────────────┤
│  5. GATE CHECK                                          │
│     python scripts/impl_session.py gate                 │
│     Must pass before commit                             │
├─────────────────────────────────────────────────────────┤
│  6. COMMIT + PUSH                                       │
│     Only after gate passes                              │
├─────────────────────────────────────────────────────────┤
│  7. CLEAN                                               │
│     python scripts/impl_session.py clean                │
│     Archives session artifacts                          │
└─────────────────────────────────────────────────────────┘
```

## Agents

| Agent | Role |
|-------|------|
| **Opus** | Implements code. Runs verification. Initiates Codex review. Fixes blockers. Commits only after gate pass. |
| **GPT-5.2-Codex-mini** | Reviews every implementation session. Writes durable review artifact. Identifies blockers, warnings, suggestions. |

## Invariants

1. Every non-trivial code session must use ISH.
2. Opus runs verification before commit.
3. Opus initiates Codex review every session.
4. Codex review results are written to `runtime/sessions/active_review.json`.
5. If Codex identifies blockers, Opus fixes them before commit.
6. Commit is forbidden until the gate passes.
7. Push is forbidden until commit passes all gates.
8. Docs and code workflow must align exactly.
9. Working tree left clean after a successful batch.

## Session Artifact

Location: `runtime/sessions/active_session.json`

```json
{
  "session_id": "ISH-a1b2c3d4",
  "branch": "feature-branch",
  "execution_mode": "IMPLEMENT",
  "scope": "Add DC-DC domain pack",
  "files_expected_to_change": ["breakthrough_engine/dcdc_domain.py"],
  "risk_level": "medium",
  "tests_expected_to_run": ["tests/test_breakthrough/test_dcdc.py"],
  "review_gate_required": true,
  "commit_blocked_until_gate_pass": true,
  "created_at": "2026-03-15T10:00:00+00:00",
  "notes": ""
}
```

## Review Artifact

Location: `runtime/sessions/active_review.json`

```json
{
  "session_id": "ISH-a1b2c3d4",
  "reviewer": "codex",
  "reviewed_at": "2026-03-15T10:30:00+00:00",
  "files_reviewed": ["breakthrough_engine/dcdc_domain.py"],
  "blockers": [],
  "warnings": ["Consider adding edge-case test for zero load"],
  "suggestions": ["Could extract shared scoring logic"],
  "gate_decision": "PASS",
  "notes": ""
}
```

### Gate Decision Rules

- `gate_decision: "PASS"` → blockers list is empty → commit allowed
- `gate_decision: "FAIL"` → blockers list is non-empty → commit blocked

## Pre-Commit Hook

The `.githooks/pre-commit` hook enforces the gate automatically.

Install once:
```bash
git config core.hooksPath .githooks
```

Behavior:
- Docs-only commits: no gate required
- Code commits with active session: gate must pass
- Code commits without session: warning only (grace period)
- Emergency bypass: `git commit --no-verify` (use sparingly, document why)

## Commands

```bash
# Start a session
python scripts/impl_session.py init --scope "Battery v3 hardening" --risk medium --files breakthrough_engine/battery_loop.py

# Run verification (static checks + tests)
python scripts/impl_session.py verify

# Write Codex review (after Codex reviews the diff)
python scripts/impl_session.py write-review --files battery_loop.py --warnings "Minor style"

# Write Codex review with blockers
python scripts/impl_session.py write-review --files battery_loop.py --blockers "Missing test for new fail gate"

# Check gate status
python scripts/impl_session.py gate

# Check review status only
python scripts/impl_session.py review-status

# Archive and clean after successful commit
python scripts/impl_session.py clean
```

## Codex Review Invocation

Opus should invoke Codex with:

1. The implementation diff (`git diff`)
2. List of changed files
3. Session scope description
4. Relevant contracts/docs (e.g., `domain_models.py`, `CLAUDE.md`)
5. Explicit review criteria:
   - Correctness
   - Regressions
   - Missing wiring / disconnected integrations
   - Contract mismatches
   - Authority drift (changes outside declared scope)
   - Missing tests for new behavior

Codex returns structured feedback. Opus writes it via `write-review`.

## Recovery

If the gate fails:

1. Read blockers from `runtime/sessions/active_review.json`
2. Fix the code issues
3. Rerun: `python scripts/impl_session.py verify`
4. Request new Codex review
5. Write updated review artifact
6. Rerun: `python scripts/impl_session.py gate`
7. Commit when gate passes

## What Is Mandatory vs Optional

| Check | Mandatory | Optional |
|-------|-----------|----------|
| Session artifact for code commits | Yes | — |
| Codex review for code commits | Yes | — |
| Zero blockers for commit | Yes | — |
| Scope drift warning | — | Yes (warning only) |
| Full regression suite | — | Yes (risk=high triggers it) |
| Doc consistency check | — | Yes |

## Artifacts Location

All session artifacts live in `runtime/sessions/` (gitignored).
Archived sessions go to `runtime/sessions/archive/`.
