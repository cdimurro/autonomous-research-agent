# Embedding Regime Boundary Documentation

**Created**: Phase 9B-Revised (2026-03-10)
**Branch**: `breakthrough-engine-phase9-policy-actuation`
**Commit at creation**: `bbd7692`
**Purpose**: Explicitly define the old and new embedding regimes so that no future analysis silently mixes incomparable baselines.

---

## CRITICAL: Do Not Cross Regimes in Policy Comparisons

Novelty scores, similarity scores, and embedding-distance-based blocking rates are **not directly comparable** across Regime 1 and Regime 2. The embedding space changed dimensionality (768d → 2560d) and the underlying model changed fundamentally. Any A/B or baseline comparison **must** use campaigns from the same regime.

---

## Regime Definitions

### Regime 1 — nomic-embed-text (OLD)

| Field | Value |
|-------|-------|
| Model | `nomic-embed-text` |
| Dimension | 768 |
| Introduced in code | Phase 4D (commit `13337ab`) |
| Removed from code | Phase 9 (commit `bbd7692`) |
| Timeout | 30s |
| Final commit using this regime | `1b52a0f` (Phase 8B) |

**Baselines built under Regime 1**:

| Baseline ID | File | Campaigns | Notes |
|-------------|------|-----------|-------|
| `phase7d_reviewed_oldregime` | `runtime/baselines/phase7d_reviewed_baseline.json` | 5 (eval_clean_energy_30m) | Explicitly records `embedding_model: "nomic-embed-text"` |
| `phase8_reviewed_oldregime` | `runtime/baselines/phase8_reviewed_baseline.json` | 10 (eval_clean_energy_30m) | Records `embedding_model: ""` (not recorded at freeze time), but built under Regime 1 — see note below |

> **Note on phase8_reviewed_baseline**: The `embedding_model` field was left empty at freeze time (Phase 8B implementation gap). The model was `nomic-embed-text` because the switch to `qwen3-embedding:4b` did not occur until Phase 9, commit `bbd7692`. This baseline is treated as Regime 1.

---

### Regime 2 — qwen3-embedding:4b (NEW, CURRENT)

| Field | Value |
|-------|-------|
| Model | `qwen3-embedding:4b` |
| Dimension | 2560 |
| Introduced in code | Phase 9 (commit `bbd7692`) |
| Status | **CURRENT** — all future campaigns use this model |
| Timeout | 120s |
| Environment override | `BT_EMBEDDING_MODEL` |

**Baselines built under Regime 2**:

| Baseline ID | File | Campaigns | Notes |
|-------------|------|-----------|-------|
| `phase9_new_embedding_reviewed` | `runtime/baselines/phase9_new_embedding_reviewed.json` | Pending batch execution | See Deliverable B — scaffold exists, awaiting real campaigns |

---

## Exact Regime Boundary

| Commit | Phase | Embedding Model | Notes |
|--------|-------|----------------|-------|
| `1b52a0f` | Phase 8B | `nomic-embed-text` (768d) | Last commit on Regime 1 |
| `bbd7692` | Phase 9 | `qwen3-embedding:4b` (2560d) | **First commit on Regime 2** |

**The boundary is at commit `bbd7692`.**

The specific diff in `breakthrough_engine/embeddings.py`:
```python
# Before (Regime 1):
model: str = "nomic-embed-text",
dim: int = 768,
timeout: int = 30,

# After (Regime 2):
model: str = "qwen3-embedding:4b",
dim: int = 2560,
timeout: int = 120,
```

---

## Regime Impact on Metrics

The following metrics are **embedding-dependent** and are **not directly comparable across regimes**:

| Metric | Why embedding-dependent |
|--------|------------------------|
| Novelty block rate | Computed as cosine similarity against corpus embeddings |
| Semantic novelty score | Direct embedding cosine comparison |
| Evidence ranking scores (domain_overlap, mechanism_overlap) | Use embedding similarity |
| Finalist count per campaign | Affected by novelty blocking rate |
| Overall block rate | Driven by embedding similarity threshold |

The following metrics are **less directly embedding-dependent** (compare with caution):

| Metric | Notes |
|--------|-------|
| Champion final score | Weighted combination; scoring_weights unchanged |
| Falsification pass rate | Logic-based, not embedding-based |
| Integrity ok rate | Logic-based |
| Review approval rate | Human label, not embedding-based |

---

## Old Baselines: Status After Regime Change

| Baseline | Status | Permitted Uses |
|----------|--------|---------------|
| `phase7d_reviewed_oldregime` | **READ-ONLY, OLD REGIME** | Regression gating *within* old-regime campaigns only; do NOT use as anchor for new-regime A/B |
| `phase8_reviewed_oldregime` | **READ-ONLY, OLD REGIME** | Same — old-regime comparison only |
| `phase5_validated_benchmark` | READ-ONLY, deterministic | Algorithmic regression (FakeCandidateGenerator + MockEmbeddingProvider — not embedding-model-sensitive) |

> Phase 5 validated benchmark uses `MockEmbeddingProvider` (hash-based, not Ollama) and is therefore **regime-independent** for algorithmic regression checks.

---

## New Baseline Required Before A/B Trial

**No valid policy-comparable baseline exists under Regime 2 yet.**

The Phase 9B plan requires:
1. Run a baseline batch of campaigns under Regime 2 (champion arm, eval_clean_energy_30m)
2. Freeze the result as `phase9_new_embedding_reviewed`
3. Use this as the anchor for all Regime 2 policy comparisons

Until this batch runs, the new-regime baseline is a scaffold (`runtime/baselines/phase9_new_embedding_reviewed.json` with `status: "pending_batch_execution"`).

---

## Future Regime Changes

If the embedding model is changed again:
1. Create a new regime entry in this document
2. Record the commit boundary
3. Mark all prior baselines as belonging to their respective regime
4. Do not run A/B policy trials across regimes

---

## Baseline Registry (Regime-Aware)

| Baseline ID (CLI name) | Regime | File | Use For |
|------------------------|--------|------|---------|
| `phase5_validated` | N/A (deterministic) | `runtime/baselines/phase5_validated_benchmark.json` | Algorithmic regression |
| `phase7d_reviewed_oldregime` | Regime 1 (nomic-embed-text) | `runtime/baselines/phase7d_reviewed_baseline.json` | Old-regime comparison only |
| `phase8_reviewed_oldregime` | Regime 1 (nomic-embed-text) | `runtime/baselines/phase8_reviewed_baseline.json` | Old-regime comparison only |
| `phase9_new_embedding_reviewed` | Regime 2 (qwen3-embedding:4b) | `runtime/baselines/phase9_new_embedding_reviewed.json` | New-regime A/B anchor — **pending** |
