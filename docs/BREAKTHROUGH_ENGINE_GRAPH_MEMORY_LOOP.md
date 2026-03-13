# Graph Memory Loop Preparation

## Design

The KG should eventually improve from the system's own outputs. Phase 10E-Prime hardens the write-back scaffolding to prepare for this.

## Write-Back Semantics

Published candidates write to `bt_kg_findings` with:

| Field | Purpose |
|-------|---------|
| `id` | Unique finding identifier |
| `candidate_id` | Source candidate |
| `publication_id` | Publication record (if published) |
| `title`, `statement`, `mechanism` | Finding content |
| `domain` | Domain scope |
| `confidence` | System confidence (0-1) |
| `valid_from` | Creation timestamp |
| `valid_until` | NULL = currently valid; timestamp = superseded |
| `superseded_by` | ID of replacement finding |
| `source_evidence_ids` | JSON array of evidence that supported this finding |
| `status` | "active" / "shadow" / "superseded" |

## Phase 10E-Prime Additions

### Write-Back Payload Generator

`generate_write_back_payload()` creates a dry-run payload without persisting, including:
- Grounding verdict and score from the validation layer
- This enables future filtering: only write back well-grounded findings

### Readiness Check

`write_back_readiness_check()` reports:
- Whether `bt_kg_findings` is accessible
- Active/shadow finding counts
- Activation status (currently blocked — requires explicit promotion)

### Current State

| Metric | Value |
|--------|-------|
| Active findings | 0 |
| Shadow findings | 0 |
| Activation blocked | Yes |
| Activation requirement | Downstream campaign validation + explicit promotion |

## Temporal Versioning

The write-back supports temporal versioning:
1. **New finding** → `valid_from = now`, `valid_until = NULL`, `status = "active"`
2. **Superseded** → `valid_until = now`, `superseded_by = new_id`, `status = "superseded"`
3. **Query at time T** → `valid_from <= T AND (valid_until IS NULL OR valid_until > T)`

## Activation Path

1. Run bounded downstream campaign comparison (Phase 10E-Prime Deliverable J)
2. Verify graph-native arm performance meets production thresholds
3. Explicitly promote: change write-back from shadow to active
4. Monitor for finding quality regression via grounding validation
5. Supersede low-quality findings based on subsequent evidence

## Safety

- Write-back is **shadow-only** — findings marked "shadow" are invisible to production retrieval
- No automatic activation — requires explicit human decision
- Supersession is auditable via `superseded_by` chain
- Grounding validation provides quality gate before activation
