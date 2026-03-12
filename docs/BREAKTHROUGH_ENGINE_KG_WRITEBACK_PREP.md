# KG Write-Back Preparation — Phase 10A

## Overview

The write-back scaffold enables published candidates to be stored in `bt_kg_findings` with temporal validity fields, preparing for future phases where the KG can track the evolution of scientific knowledge.

## Temporal Design

```
bt_kg_findings
  valid_from    — when the finding was created (auto-set)
  valid_until   — NULL means currently valid; set when superseded
  superseded_by — ID of the newer finding that replaces this one
  status        — active | shadow | superseded
```

## Write-Back Functions

### `write_candidate_as_finding()`
- Writes any candidate hypothesis into bt_kg_findings
- Default confidence: 0.5
- Default status: shadow (safe)
- Records evidence_refs from the candidate

### `write_publication_as_finding()`
- Writes a published candidate with higher confidence (0.7)
- Links to the publication_id for audit trail
- Only published candidates should use this path

### `supersede_finding()`
- Sets valid_until on the old finding
- Sets superseded_by to the new finding ID
- Changes status to "superseded"

## Current Limitations (Phase 10A)

1. **No automatic contradiction invalidation** — findings are not automatically invalidated when contradictory evidence appears
2. **No policy integration** — write-back does not affect policy learning or scoring weights
3. **Shadow-only** — all findings are written with status="shadow" by default
4. **No cross-domain linking** — findings are domain-scoped only

## Future Phases

- Phase 10B: Active write-back (status="active") for published candidates
- Phase 10C: Contradiction detection and automatic supersession
- Phase 10D: Policy-aware findings that influence scoring weights
- Phase 10E: Cross-domain knowledge graph linking

## CLI Usage

```bash
# Check write-back status
python -m breakthrough_engine kg writeback-status --domain clean-energy
```
