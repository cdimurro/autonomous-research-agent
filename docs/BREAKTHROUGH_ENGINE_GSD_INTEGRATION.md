# Breakthrough Engine - GSD Integration

## Status: Integrated (repo-local)

## What is GSD?

GSD ("Get Stuff Done") is a task-tracking discipline for maintaining forward momentum on operational engineering work. In this repo, GSD is implemented as a lightweight, repo-local tracking system that coexists with the existing planning/status docs.

## Inspection Result

- **Prior to Phase 4A:** No GSD integration existed in this repo.
- **Existing discipline:** Planning and status tracking via `docs/BREAKTHROUGH_ENGINE_*_STATUS.md` and `docs/BREAKTHROUGH_ENGINE_*_PLAN.md` files.
- **Decision:** Add a minimal repo-local GSD layer that complements (does not replace) the existing doc-based status tracking.

## What Was Added

### 1. `.gsd/` directory

A repo-local directory for tracking active operational tasks:

```
.gsd/
  ACTIVE.md      # Current sprint / active task list
  DONE.md        # Completed task archive
  BLOCKERS.md    # Active blockers and their resolution status
```

### 2. Conventions

- **ACTIVE.md** contains the current operational focus items (max 5-7 items)
- Items are marked `[ ]` (pending), `[>]` (in progress), `[x]` (done)
- When an item is completed, move it to **DONE.md** with the date
- **BLOCKERS.md** tracks anything blocking forward progress
- Each entry includes: what, why blocked, resolution path, owner

### 3. Relationship to Existing Docs

| Layer | File(s) | Purpose |
|-------|---------|---------|
| Strategic plan | `docs/*_MASTER_PLAN.md` | Overall vision and phases |
| Phase plan | `docs/*_PHASE*_PLAN.md` | Detailed phase scope |
| Phase status | `docs/*_PHASE*_STATUS.md` | Phase completion tracking |
| GSD active | `.gsd/ACTIVE.md` | Current operational focus |
| GSD blockers | `.gsd/BLOCKERS.md` | Active blockers |

GSD tracks the **current operational sprint** (what you're doing right now). Phase status docs track **phase-level completeness** (what's done overall). They complement each other.

## How to Use GSD in This Repo

### Daily workflow

1. Check `.gsd/ACTIVE.md` for current tasks
2. Mark your current task as `[>]` (in progress)
3. When done, mark `[x]` and move to `DONE.md`
4. If blocked, add entry to `BLOCKERS.md`
5. At end of session, update status docs with cumulative progress

### With Claude Code / Opus

When starting a session:
1. Read `.gsd/ACTIVE.md` to see what's next
2. Read `.gsd/BLOCKERS.md` to see what's stuck
3. Work through active items
4. Update GSD files as you go
5. Update phase status docs at session end

### Commands

```bash
# View active tasks
cat .gsd/ACTIVE.md

# View blockers
cat .gsd/BLOCKERS.md

# View completed work
cat .gsd/DONE.md
```

## Integration Notes

- GSD files are committed to the repo for team visibility
- GSD does NOT replace the existing `docs/` status discipline
- GSD is for operational focus; status docs are for historical record
- Keep GSD items concrete and actionable (not aspirational)
