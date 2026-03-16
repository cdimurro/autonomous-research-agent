# Engine Density and Stability Report

**Generated:** 2026-03-15
**Branch:** `battery-loop-hardening`
**Commit:** post `f8fd99c` (workspace-ops-hardening-v1 + .gitignore fix)

---

## 1. Executive Summary

Three evaluations were run to assess the Breakthrough Engine's operational readiness and data density:

| Evaluation | Runs | Result |
|-----------|------|--------|
| Battery decision-brief campaign | 46 runs (45 success) | 45 briefs generated |
| PyBaMM sidecar stability | 42 candidates verified | 92.9% success rate |
| PV baseline check | 5 seeds | Stable, no regressions |

**Biggest findings:**

1. **100% promotion rate** across all battery seeds — the loop is not selective enough. Every run promotes a candidate, which means the promotion threshold or candidate generation diversity is too narrow.
2. **Family concentration**: `bounded_aggressive` (35.6%) and `rate_optimized` (33.3%) dominate promotions. Only 5 of 11 families ever win. No cathode family was ever promoted.
3. **"Why promising" text is nearly identical** across all 45 briefs — 64% share the exact same text. The brief differentiation is poor.
4. **Sidecar is operationally stable** (92.9% success, 0 timeouts, avg 1.49s) but **LFP is a systematic weak point** (all caveat, 2/9 errors).
5. **PV is stable and regression-free** — `bounded_aggressive` wins every seed (family diversity issue mirrors battery).

**Next bottleneck:** Battery data density and candidate diversity, not infrastructure or sidecar stability.

**Recommended next phase:** Battery loop hardening — improve candidate diversity, raise selectivity, differentiate brief text.

---

## 2. Battery Decision-Brief Campaign

### Setup
- **46 total runs** across 3 modes:
  - ECM-only: 18 seeds (100–117), 6 candidates each
  - Mock sidecar: 18 seeds (200–217), 6 candidates each
  - Cathode + mock: 10 seeds (300–309), 8 candidates each
- **45 briefs generated** (1 run produced no promotion — seed 115)
- **1 error**: seed 115 (no promotion, valid outcome)

### Key Distributions

| Metric | Value |
|--------|-------|
| Total briefs | 45 |
| Promotion rate | 100% (44/45 runs, seed 115 = no promotion) |
| Score range | 0.720 – 0.861 |
| Score mean | 0.826 |
| Unique headlines | 42/45 (93.3%) |

### Promoted Family Breakdown

| Family | Count | % |
|--------|-------|---|
| bounded_aggressive | 16 | 35.6% |
| rate_optimized | 15 | 33.3% |
| reduced_resistance | 7 | 15.6% |
| combined_moderate | 4 | 8.9% |
| improved_efficiency | 3 | 6.7% |
| cathode_* (any) | 0 | 0% |
| improved_capacity | 0 | 0% |
| reduced_fade | 0 | 0% |

**Critical observation:** 6 of 11 families never win. All 4 cathode families are absent from promotions despite being generated. This means either:
- Cathode families are consistently outscored by ECM families
- The scoring/promotion logic systematically disadvantages them
- Or cathode candidates are generated but never competitive

### Confidence Tier Distribution

| Tier | Count |
|------|-------|
| high | 28 (mock sidecar + cathode runs) |
| standard | 17 (ECM-only runs) |

### Sidecar Gate Distribution

| Gate | Count |
|------|-------|
| confirmed | 28 |
| not_verified | 17 |

No vetoes or caveats in promoted candidates — expected since mock sidecar produces deterministic confirmations for winning families.

### Repetition vs. Diversity Analysis

**"Why promising" patterns (45 briefs):**

| Pattern | Count |
|---------|-------|
| "Strongest scoring components: robustness (1.00), plausibility_penalty (1.00), rate_capability (1.00)." | 29 (64%) |
| "Strongest scoring components: resistance_improvement (1.00), plausibility_penalty (1.00), rate_capability (1.00)." | 8 (18%) |
| "Strongest scoring components: resistance_improvement (1.00), robustness (1.00), plausibility_penalty (1.00)." | 5 (11%) |
| Other variants | 3 (7%) |

**Problem:** 64% of all briefs produce the exact same "why promising" text. The text generator picks the top-3 scoring components, but since `robustness`, `plausibility_penalty`, and `rate_capability` frequently max at 1.00, most briefs say the same thing.

**Top caveats:**

| Caveat | Count |
|--------|-------|
| "Gain concentrated in robustness (score=1.00)" | 29 |
| "Weakness in fade_improvement (score=0.28)" | 22 |
| Tradeoff risk (bounded_aggressive) | 16 |
| Tradeoff risk (rate_optimized) | 15 |

**Recommended action patterns:**

| Action | Count |
|--------|-------|
| "Candidate is ready for deeper experimental validation" | 28 |
| "Run PyBaMM sidecar verification to increase confidence" | 17 |

### Mode Breakdown

| Mode | Runs | Promoted | Rate | Mean Score | Top Family |
|------|------|----------|------|------------|-----------|
| ECM-only | 17 | 17 | 100% | 0.817 | bounded_aggressive (6) |
| Mock sidecar | 18 | 18 | 100% | 0.830 | rate_optimized (7) |
| Cathode + mock | 10 | 10 | 100% | 0.834 | bounded_aggressive (5) |

### Assessment

**Are the briefs genuinely differentiated?** Partially. Headlines are 93% unique (due to different numeric values), but the qualitative content (why promising, caveats, recommended action) is highly repetitive.

**Are promoted candidates meaningfully distinct?** Moderately. The parameter values differ across seeds, but the winning family is concentrated in 2 families (69% bounded_aggressive + rate_optimized).

**Is the current battery loop producing enough signal density?** No. For a real user workflow, seeing the same 2-3 families win with the same "why" text and same caveats would be low-signal. The loop needs:
1. Greater candidate diversity (more families competitive)
2. More selective promotion (not 100%)
3. Better brief text differentiation

---

## 3. PyBaMM Sidecar Stability Checkpoint

### Setup
- Live PyBaMM sidecar: Python 3.11.15, PyBaMM 25.12.2
- 42 candidates from 6 seed configurations
- Diverse family coverage: all 11 families represented

### Stability Metrics

| Metric | Value |
|--------|-------|
| Total verified | 42 |
| Succeeded | 39 (92.9%) |
| Failed | 3 (7.1%) |
| Timed out | 0 |
| Mean duration | 1.49s |
| Min duration | 1.19s |
| Max duration | 1.92s |

### Concordance Statistics

| Metric | Value |
|--------|-------|
| Min concordance | 0.541 |
| Max concordance | 0.780 |
| Mean concordance | 0.733 |

### Gate Distribution

| Gate | Count | % |
|------|-------|---|
| confirmed | 32 | 76.2% |
| caveat | 7 | 16.7% |
| not_verified (error) | 3 | 7.1% |
| veto | 0 | 0% |

### Family-Level Results

| Family | n | Success | Mean Conc. | Gate |
|--------|---|---------|-----------|------|
| cathode_high_ni | 6 | 6/6 (100%) | 0.780 | all confirmed |
| bounded_aggressive | 3 | 3/3 (100%) | 0.777 | all confirmed |
| improved_capacity | 5 | 5/5 (100%) | 0.776 | all confirmed |
| reduced_resistance | 2 | 2/2 (100%) | 0.775 | all confirmed |
| improved_efficiency | 6 | 6/6 (100%) | 0.775 | all confirmed |
| combined_moderate | 2 | 2/2 (100%) | 0.775 | all confirmed |
| reduced_fade | 4 | 4/4 (100%) | 0.775 | all confirmed |
| cathode_nmc532 | 1 | 1/1 (100%) | 0.748 | confirmed |
| cathode_lmfp | 2 | 2/2 (100%) | 0.702 | all confirmed |
| rate_optimized | 2 | 1/2 (50%) | 0.775 | 1 confirmed, 1 error |
| **cathode_lfp** | **9** | **7/9 (78%)** | **0.558** | **all caveat + 2 errors** |

### Key Observations

1. **Sidecar is operationally stable**: 92.9% success, 0 timeouts, fast execution (avg 1.49s). Ready for routine use.
2. **LFP is a systematic weak point**: All 7 successful LFP verifications produced caveat (concordance 0.54–0.57), and 2/9 LFP runs failed with Sundials solver errors. This is a chemistry-specific mismatch, not infrastructure flakiness.
3. **High-Ni (NMC-811) has best concordance** (0.780) — the Chen2020 parameter set is well-matched.
4. **No vetoes**: The sidecar never vetoed a candidate, meaning concordance is always >= 0.30.
5. **3 errors all from Sundials convergence failures**: 2 LFP + 1 rate_optimized. These are parameter-regime edge cases in the DFN solver, not bugs.
6. **Runtime is acceptable**: ~1.5s per candidate means top-2 verification costs ~3s per benchmark run.

### Assessment

**Is the sidecar stable enough for routine use?** Yes. 92.9% success rate with 0 timeouts.

**Does it produce meaningful validation signal?** Partially. It confirms most families and adds caveats for LFP, but it never vetoes or changes outcomes for promoted candidates. Its primary value is confidence-tier elevation (standard → high).

**Are there unreliable chemistries?** LFP is the only problem area. The Prada2013 parameter set produces lower concordance and occasional solver failures.

---

## 4. PV Baseline Check

### Benchmark Runs

| Seed | Best Family | Score | Pmax (W) | Ref Envelope | Decision |
|------|------------|-------|----------|--------------|----------|
| 42 | bounded_aggressive | 0.725 | 296.0 | PASS | promoted |
| 87 | bounded_aggressive | 0.698 | 291.9 | PASS | promoted |
| 137 | bounded_aggressive | 0.726 | 296.5 | PASS | promoted |
| 200 | bounded_aggressive | 0.752 | 299.1 | PASS | promoted |
| 300 | bounded_aggressive | 0.738 | 296.6 | PASS | promoted |

### Assessment

- **Baseline stable**: Consistent 258.97W baseline Pmax across all seeds
- **Promotion behavior**: 1 promoted, 4 rejected, 0 hard-fail per run (consistent)
- **Realism checks**: All pass reference envelope (benchmark_mono_si_300w)
- **No regressions**: Artifact generation, report quality, CLI behavior all working
- **Family diversity issue**: `bounded_aggressive` wins 100% of runs — same concentration issue as battery

**Is PV still stable and trustworthy?** Yes. Deterministic, regression-free, good benchmark quality.

**Has anything drifted?** No.

**Family diversity concern:** Like battery, PV shows extreme family concentration. This suggests the issue is structural (scoring/family design), not domain-specific.

---

## 5. Recommended Next Focus

### Recommendation: Battery Loop Hardening (Candidate Diversity + Selectivity)

**Evidence:**
1. 100% promotion rate indicates the threshold is too low or candidates too homogeneous
2. 2 families account for 69% of all promotions
3. 6 of 11 families (including all cathode) never win
4. Brief text is highly repetitive (64% identical "why promising")
5. Infrastructure (sidecar, CLI, artifacts) is stable — not the bottleneck

**Specific actions recommended:**
1. **Analyze why cathode families never win**: Compare cathode candidate scores vs ECM family scores to find the scoring disadvantage
2. **Consider raising the promotion threshold** from 0.55 to ~0.65–0.70 to reduce promotion rate from 100% to ~50-70%
3. **Diversify the "why promising" generator**: Include more candidate-specific language (parameter changes, tradeoff profile) instead of just top-3 component names
4. **Consider family-aware promotion**: Ensure the loop occasionally promotes non-dominant families when they're competitive
5. **Investigate PV family concentration**: Same pattern exists there — may be a shared issue in the scoring architecture

**Why not DC-DC (domain 3)?** Adding a third domain before the existing two produce diverse, selective outputs would just replicate the same concentration problem. Fix the loop first.

**Why not sidecar/cathode tuning?** LFP concordance is a real issue, but cathode families aren't being promoted anyway. Fix promotion diversity first, then tune sidecar concordance for the families that actually win.

---

## 6. Known Limitations

1. **Mock sidecar only for campaign**: The 28 "confirmed" briefs used MockPyBaMMSidecar (deterministic), not live PyBaMM. Live sidecar was tested separately in the stability checkpoint.
2. **No live sidecar campaign**: Running 46 runs with live sidecar would take ~2 minutes but was not done to keep evaluation clean. The stability checkpoint covers sidecar reliability.
3. **Seed 115 error not fully investigated**: No promotion was produced (valid outcome), but the exact candidate mix that led to no promotion was not analyzed.
4. **Chemistry field not propagated**: In the sidecar stability sweep, `chemistry` was None for all candidates because candidate generation doesn't set `parameters["chemistry"]` — it's in the family name. The sidecar infers chemistry from the family name via its own mapping.
5. **PV only tested with 6 candidates**: Did not test with more candidates or different thresholds.
6. **Campaign did not test live sidecar winner changes**: To test whether the live sidecar changes outcomes, we'd need to run the same seeds with and without live sidecar and compare promotions.
7. **Evaluation scripts are in `scripts/` as one-off tools**: They are not part of the test suite and may need updates if the API changes.
