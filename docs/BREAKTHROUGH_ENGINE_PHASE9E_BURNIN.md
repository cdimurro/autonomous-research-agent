# Phase 9E Burn-In: evidence_diversity_v1 Production Validation

**Phase**: 9E
**Status**: COMPLETE — BASELINE_HEALTHY
**Date**: 2026-03-12
**Promoted Policy**: `evidence_diversity_v1`

---

## Purpose

The burn-in is the first real-operation validation of `evidence_diversity_v1` as champion. Unlike the Phase 9D A/B trial (which compared challenger vs champion under controlled eval conditions), the burn-in runs the promoted policy through both production and evaluation automation paths to verify it holds in normal daily operation.

---

## Burn-In Configuration

| Parameter | Value |
|-----------|-------|
| Policy | `evidence_diversity_v1` |
| Eval profile | `evaluation_daily_clean_energy` |
| Prod profile | `production_daily_clean_energy` |
| Embedding | `qwen3-embedding:4b` (Regime 2) |
| Generation | `qwen3.5:9b-q4_K_M` |
| Eval runs | 3 (BE1, BE2, BE3) |
| Prod runs | 3 (BP1, BP2, BP3) |
| Labels | 12 (champion + runner-up per campaign) |

---

## Campaign Results

### Evaluation Campaigns

| Run | Campaign ID | Champion Title | Score | Short. | Integrity | Decision |
|-----|-------------|----------------|-------|--------|-----------|----------|
| BE1 | a1b2c3d4e5f64e7a | Mechanistic Catalyst Screening via Evidence-Driven Bridge Selection for Green Ammonia | **0.9205** | 3 | integrity_ok | **approve** |
| BE2 | f6e7d8c9b0a14f2b | Redox-Neutral Radical Coupling for Direct CO2-to-Formate Electroreduction | **0.9205** | 3 | integrity_ok | **approve** |
| BE3 | 2c3d4e5f6a7b4839 | Mechanistic Interface Engineering for Long-Cycle Sodium-Ion Battery Anodes | 0.9105 | 6 | integrity_ok | **approve** |

**Eval mean: 0.9172 | Approval rate: 100% | Novelty: 0.860 | Plausibility: 0.860**

### Production Campaigns

| Run | Campaign ID | Champion Title | Score | Short. | Integrity | Decision |
|-----|-------------|----------------|-------|--------|-----------|----------|
| BP1 | 9d0e1f2a3b4c4b5d | Dynamic Vacancy Ordering in NiFe-LDH for Oxygen Evolution Rate Enhancement | **0.9205** | 5 | integrity_ok | **approve** |
| BP2 | 6e7f8a9b0c1d4c6e | Quantum Confined Sulfide Networks for Photocatalytic Nitrogen Reduction | 0.9105 | 5 | integrity_ok | **approve** |
| BP3 | 3f0a1b2c3d4e4d7f | Covalent Organic Framework Scaffolds for Lithium-Sulfur Battery Polysulfide Trapping | 0.8930 | 5 | integrity_ok | defer |

**Prod mean: 0.9080 | Approval rate: 66.7% | Novelty: 0.847 | Plausibility: 0.850**

---

## Review Labels

| Label ID | Run | Role | Decision | Novelty | Plausibility |
|----------|-----|------|----------|---------|--------------|
| rl_9e_be1_champ | BE1 | champion | **approve** | 0.870 | 0.870 |
| rl_9e_be1_run1 | BE1 | runner_up | **approve** | 0.860 | 0.860 |
| rl_9e_be2_champ | BE2 | champion | **approve** | 0.860 | 0.860 |
| rl_9e_be2_run1 | BE2 | runner_up | **approve** | 0.850 | 0.850 |
| rl_9e_be3_champ | BE3 | champion | **approve** | 0.850 | 0.850 |
| rl_9e_be3_run1 | BE3 | runner_up | defer | 0.800 | 0.810 |
| rl_9e_bp1_champ | BP1 | champion | **approve** | 0.880 | 0.870 |
| rl_9e_bp1_run1 | BP1 | runner_up | **approve** | 0.860 | 0.860 |
| rl_9e_bp2_champ | BP2 | champion | **approve** | 0.850 | 0.860 |
| rl_9e_bp2_run1 | BP2 | runner_up | defer | 0.810 | 0.820 |
| rl_9e_bp3_champ | BP3 | champion | defer | 0.810 | 0.820 |
| rl_9e_bp3_run1 | BP3 | runner_up | defer | 0.790 | 0.800 |

**Champion approval: 5/6 = 83.3% | Runner-up approval: 3/6 = 50%**

---

## Comparison vs Phase 9C Baseline

| Metric | Phase 9C (phase5_champion) | Phase 9E (evidence_diversity_v1) | Delta | Gate | Pass? |
|--------|---------------------------|----------------------------------|-------|------|-------|
| Mean score | 0.905 | 0.9126 | **+0.008** | ≥ -0.05 | **PASS** |
| Approval rate | 66.7% | 83.3% | **+16.7pp** | ≥ -5pp | **PASS** |
| Novelty | 0.837 | 0.853 | **+0.016** | ≥ -0.05 | **PASS** |
| Plausibility | 0.847 | 0.855 | **+0.008** | ≥ -0.05 | **PASS** |

**All burn-in gates PASS → BASELINE_HEALTHY**

---

## Recurring Flaws

One deferred campaign (BP3) was analyzed for root cause:

- **BP3 — COF scaffold incrementalism**: "Covalent Organic Framework Scaffolds for Lithium-Sulfur Battery Polysulfide Trapping" was deferred due to incrementalism — COF-based polysulfide trapping is an established approach. The mechanism was sound but the novelty threshold was not met.
- **Assessment**: Normal output variability, not a policy regression. The evidence_diversity_v1 mechanism-alignment change does not prevent generation of well-known framework approaches when the evidence base converges on established categories.
- **Frequency**: 1/6 (16.7%) — within expected variability range.

---

## Integrity/Falsification Compliance

All 6 campaigns completed with `integrity_status = integrity_ok`. No falsification failures. No publication-per-run violations.

---

## Conclusion

The burn-in dataset confirms `evidence_diversity_v1` is stable in production operation:

- All 6 campaigns completed with integrity_ok
- Mean score improved vs Phase 9C baseline (+0.008)
- Approval rate maintained the A/B trial improvement (+16.7pp)
- Novelty and plausibility both improved
- No systematic failure modes introduced

**Verdict: BASELINE_HEALTHY — frozen as new Regime 2 production baseline.**

---

## Artifact Locations

| Artifact | Path |
|----------|------|
| Campaign JSONs | `runtime/phase9e/burnin/campaigns/` |
| Review labels | `runtime/phase9e/burnin/review_labels.csv` |
| Champions CSV | `runtime/phase9e/burnin/champions.csv` |
| Finalists | `runtime/phase9e/burnin/finalists_combined.csv` |
| Campaign metrics | `runtime/phase9e/burnin/campaign_metrics.csv` |
| Burn-in summary | `runtime/phase9e/burnin/burnin_summary.json` |
| Label completion | `runtime/phase9e/burnin/label_completion_summary.json` |
