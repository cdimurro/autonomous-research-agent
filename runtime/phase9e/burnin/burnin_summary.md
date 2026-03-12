# Phase 9E Burn-In Summary: evidence_diversity_v1 Production Validation

**Phase**: 9E
**Burn-In ID**: phase9e_burnin
**Status**: COMPLETE — BASELINE_HEALTHY
**Date**: 2026-03-12
**Promoted Policy**: `evidence_diversity_v1`

---

## Burn-In Configuration

| Parameter | Value |
|-----------|-------|
| Champion | `evidence_diversity_v1` |
| Embedding | `qwen3-embedding:4b` (Regime 2) |
| Generation | `qwen3.5:9b-q4_K_M` |
| Eval profile | `evaluation_daily_clean_energy` |
| Prod profile | `production_daily_clean_energy` |
| Eval campaigns | 3 (BE1–BE3) |
| Prod campaigns | 3 (BP1–BP3) |
| Labels per run | 2 (champion + 1 runner-up) |
| Total labels | 12 |

---

## Campaign Results

| Run | Profile | Champion Title | Score | Short. | Integrity | Decision |
|-----|---------|----------------|-------|--------|-----------|----------|
| BE1 | eval | Mechanistic Catalyst Screening via Evidence-Driven Bridge Selection for Green Ammonia | **0.9205** | 3 | integrity_ok | **approve** |
| BE2 | eval | Redox-Neutral Radical Coupling for Direct CO2-to-Formate Electroreduction | **0.9205** | 3 | integrity_ok | **approve** |
| BE3 | eval | Mechanistic Interface Engineering for Long-Cycle Sodium-Ion Battery Anodes | 0.9105 | 6 | integrity_ok | **approve** |
| BP1 | prod | Dynamic Vacancy Ordering in NiFe-LDH for Oxygen Evolution Rate Enhancement | **0.9205** | 5 | integrity_ok | **approve** |
| BP2 | prod | Quantum Confined Sulfide Networks for Photocatalytic Nitrogen Reduction | 0.9105 | 5 | integrity_ok | **approve** |
| BP3 | prod | Covalent Organic Framework Scaffolds for Lithium-Sulfur Battery Polysulfide Trapping | 0.8930 | 5 | integrity_ok | defer |

**Burn-in: 5/6 approved (83.3%), mean score 0.9126, all integrity_ok**

---

## Burn-In vs Phase 9C Baseline Comparison (Regime 2 Only)

| Metric | Phase 9C Baseline (phase5_champion) | Phase 9E Burn-In (evidence_diversity_v1) | Delta | Gate | Pass? |
|--------|--------------------------------------|------------------------------------------|-------|------|-------|
| Mean champion score | 0.905 | 0.9126 | **+0.008** | ≥ -0.05 | **PASS** |
| Approval rate | 66.7% | 83.3% | **+16.7pp** | ≥ -5pp | **PASS** |
| Novelty confidence | 0.837 | 0.853 | **+0.016** | ≥ -0.05 | **PASS** |
| Technical plausibility | 0.847 | 0.855 | **+0.008** | ≥ -0.05 | **PASS** |

**All 4 burn-in comparison gates PASS → BASELINE_HEALTHY**

---

## Eval vs Production Breakdown

| Profile | Mean Score | Approval Rate | Novelty | Plausibility | Integrity |
|---------|-----------|---------------|---------|--------------|-----------|
| Eval (3 campaigns) | 0.9172 | 100% | 0.860 | 0.860 | 3/3 OK |
| Production (3 campaigns) | 0.9080 | 66.7% | 0.847 | 0.850 | 3/3 OK |

---

## Runner-Up Quality

| Run | Runner-Up Decision | Novelty | Plausibility |
|-----|-------------------|---------|--------------|
| BE1 | **approve** | 0.860 | 0.860 |
| BE2 | **approve** | 0.850 | 0.850 |
| BE3 | defer | 0.800 | 0.810 |
| BP1 | **approve** | 0.860 | 0.860 |
| BP2 | defer | 0.810 | 0.820 |
| BP3 | defer | 0.790 | 0.800 |

**Runner-up approval rate: 3/6 = 50%** (consistent with Phase 9D challenger arm: 50%)

---

## Recurring Flaws

One low-severity recurring pattern:
- **Incrementalism in mature framework categories** (BP3): COF/MOF scaffold approaches for energy storage are an established category. The generated candidate was mechanistically sound but insufficiently differentiated from existing work.
- Frequency: 1/6 runs
- Assessment: Normal variability, not a policy regression.

---

## Conclusion

The burn-in confirms that `evidence_diversity_v1` holds up in production operation:
- Mean score improved vs Phase 9C baseline (+0.008)
- Approval rate maintained the A/B trial improvement (+16.7pp vs baseline)
- Novelty and plausibility both improved vs baseline
- All 6 campaigns completed successfully with integrity_ok
- Runner-up quality consistent with Phase 9D challenger arm

**Verdict: BASELINE_HEALTHY — freeze as new Regime 2 production baseline.**
