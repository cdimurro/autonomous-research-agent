# Phase 8B: Baseline Freeze

**Phase**: 8B
**Frozen baseline**: `phase8_reviewed`
**Freeze date**: 2026-03-10
**Status**: COMPLETE

---

## Three Trusted Baselines

After Phase 8B, the Breakthrough Engine maintains three frozen baselines:

| Baseline ID | File | Type | Campaigns | Score Mean | Use For |
|-------------|------|------|-----------|------------|---------|
| `phase5_validated` | `phase5_validated_benchmark.json` | deterministic_benchmark | 3 | 0.912 (top) | Algorithmic regression testing |
| `phase7d_reviewed` | `phase7d_reviewed_baseline.json` | reviewed_evaluation | 5 | 0.905 | Policy learning anchor (v1) |
| `phase8_reviewed` | `phase8_reviewed_baseline.json` | reviewed_batch | 10 | 0.912 | Policy learning anchor (v2, current) |

---

## Phase 8 Reviewed Baseline Details

| Field | Value |
|-------|-------|
| Baseline ID | `phase8_reviewed` |
| File | `runtime/baselines/phase8_reviewed_baseline.json` |
| Branch | `breakthrough-engine-phase8b-reviewed-loop` |
| Commit | `0f92f11` |
| Profile | `eval_clean_energy_30m` |
| Schema | v003 |
| Campaigns | 10 |
| Champion score mean | 0.91192 |
| Champion score min | 0.88087 |
| Champion score max | 0.93054 |
| Integrity OK rate | 1.00 |
| Falsification complete rate | 1.00 |
| Overall block rate | 22.1% |
| Review labels | 20/20 complete (14 approve, 0 reject, 6 defer) |

---

## Regression Thresholds

| Metric | Threshold |
|--------|-----------|
| `champion_score_mean` | No regression > 0.05 |
| `integrity_ok_rate` | Must remain 1.00 |
| `falsification_complete_rate` | Must remain 1.00 |
| `block_rate` | No regression > 0.10 |

---

## CLI Commands

```bash
# Show Phase 8 reviewed baseline
python -m breakthrough_engine baseline show phase8_reviewed

# Compare a new batch to Phase 8 reviewed baseline
python -m breakthrough_engine baseline compare-reviewed \
  --baseline phase8_reviewed \
  --batch runtime/evaluation_batches/<batch_id>/batch_summary.json

# Freeze a future batch as a new baseline
python -m breakthrough_engine baseline freeze \
  --name phase9_reviewed \
  --batch-id <batch_id> \
  --note "Phase 9 reviewed batch"
```

---

## Baseline Selection Guide (Updated)

| Use Case | Baseline |
|----------|----------|
| Algorithmic regression before promotion | `phase5_validated` |
| Compare challenger to current quality anchor | `phase8_reviewed` |
| Compare to original reviewed quality anchor | `phase7d_reviewed` |
| Detect long-term score drift | Compare all three |

---

## Notes

- Phase 7D baseline (5 campaigns) remains valid as the original anchor
- Phase 8 baseline supersedes Phase 7D for day-to-day challenger comparison
- Both are retained; neither is deleted
- Phase 8 baseline includes review labels — Phase 7D does not
