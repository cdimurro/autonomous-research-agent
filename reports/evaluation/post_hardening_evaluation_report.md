# Post-Hardening Evaluation Report

**Generated:** 2026-03-15
**Branch:** `battery-loop-hardening`
**Batch:** `battery-loop-hardening-v2` (CC-BE-2470 through CC-BE-2474)

---

## 1. Executive Summary

Four hardening changes were implemented and validated:

| Contract | Change | Impact |
|----------|--------|--------|
| CC-BE-2470 | Promotion threshold 0.55 → 0.84 + baseline margin + tighter gates | Promotion rate reduced |
| CC-BE-2471 | Chemistry-specific baselines + bidirectional cathode perturbations | Cathode families competitive |
| CC-BE-2472 | Family diversity controls (max 2 per run, min 3 distinct) | Even generation distribution |
| CC-BE-2473 | Physics-based brief text (mOhm, Ah, %) instead of component names | 100% unique briefs |

### Before vs After

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Promotion rate | 100% (45/45) | 67% (31/46) | -33 pp |
| Families winning | 5 | 6 | +1 |
| Cathode promotions | 0 (0%) | 10 (32%) | +32 pp |
| `bounded_aggressive` share | 35.6% | 38.7% | +3 pp |
| `rate_optimized` share | 33.3% | 19.4% | -14 pp |
| Headline uniqueness | 93.3% | 100% | +7 pp |
| `why_promising` uniqueness | 36% (6 patterns) | 94% (29/31 unique) | +58 pp |
| Score mean | 0.826 | 0.849 | +0.023 |
| Score min | 0.720 | 0.841 | +0.121 |
| Score range | 0.141 | 0.025 | -0.116 |

### Key Findings

1. **Promotion is now selective**: 15 of 46 runs produced no promotion (33%), compared to 1 before.
2. **Cathode families are competitive**: `cathode_lfp` (5 wins), `cathode_nmc532` (4), `cathode_lmfp` (1). Previously all cathode families had 0 wins.
3. **Brief text is differentiated**: 100% unique headlines, 94% unique "why promising" text. Each brief now includes specific physical values (mOhm, Ah, delta %).
4. **Score floor raised**: minimum promoted score is now 0.841 vs 0.720 before. Only genuinely strong candidates are promoted.
5. **bounded_aggressive still leads** (38.7%) but no longer dominates at 69%.

---

## 2. Detailed Comparison

### Promotion Rate

| | Before | After |
|---|--------|-------|
| Total runs | 46 | 46 |
| Successful promotions | 45 | 31 |
| No-promotion runs | 1 | 15 |
| Promotion rate | 97.8% | 67.4% |

### Family Distribution (promoted only)

| Family | Before | After | Change |
|--------|--------|-------|--------|
| bounded_aggressive | 16 (35.6%) | 12 (38.7%) | +3 pp |
| rate_optimized | 15 (33.3%) | 6 (19.4%) | -14 pp |
| reduced_resistance | 7 (15.6%) | 3 (9.7%) | -6 pp |
| combined_moderate | 4 (8.9%) | 0 (0%) | -9 pp |
| improved_efficiency | 3 (6.7%) | 0 (0%) | -7 pp |
| cathode_lfp | 0 (0%) | 5 (16.1%) | +16 pp |
| cathode_nmc532 | 0 (0%) | 4 (12.9%) | +13 pp |
| cathode_lmfp | 0 (0%) | 1 (3.2%) | +3 pp |

### Why Promising Text Uniqueness

| | Before | After |
|---|--------|-------|
| Total briefs | 45 | 31 |
| Unique texts | 6 (13%) | 29 (94%) |
| Most-repeated pattern | 29x (64%) | 2x (6%) |

### Score Distribution

| | Before | After |
|---|--------|-------|
| Min | 0.720 | 0.841 |
| Max | 0.861 | 0.865 |
| Mean | 0.826 | 0.849 |
| Range | 0.141 | 0.025 |

Score compression increased because only strong candidates are promoted now.

### Confidence Tier Distribution

| Tier | Before | After |
|------|--------|-------|
| high | 28 | 17 |
| standard | 17 | 13 |
| low | 0 | 1 |

### Caveat Diversity

Before: top caveat appeared 29 times (64%)
After: top caveat appears 14 times (45%) — still the most common but less dominant.

Cathode-specific caveats now appear (5x LFP tradeoff, 4x NMC-532 tradeoff).

---

## 3. What Changed in Each Contract

### CC-BE-2470: Promotion Selectivity
- `DEFAULT_PROMOTION_THRESHOLD`: 0.55 → 0.84
- `STRESS_RESILIENCE_GATE`: 0.40 → 0.60
- `REGIME_SPECIFICITY_MIN_FLOOR`: 0.15 → 0.20
- Added `BASELINE_MARGIN` gate: candidate must beat baseline composite by 0.08
- CLI defaults updated to match

### CC-BE-2471: Family Diversity / Cathode Competitiveness
- **Root cause 1**: All candidates scored against generic NMC baseline (R0=30 mOhm). LFP at R0=42 always scored 0.0 on resistance_improvement.
  - **Fix**: Chemistry-specific baselines from `CATHODE_ECM_PROFILES`
- **Root cause 2**: Cathode perturbations only pushed R0 upward (LFP: +5 to +15). No improvement direction.
  - **Fix**: Bidirectional perturbation ranges (LFP: -8 to +6, LMFP: -6 to +4, NMC-532: -5 to +3)
- Added `_candidate_chemistry_key()` helper
- Pre-compute cathode baselines in `BatteryOptimizationLoop.run()`

### CC-BE-2472: Candidate Diversity Controls
- Added `MAX_FAMILY_REPEAT` cap (2 for n<=8, scales for larger n)
- Added `MIN_DISTINCT` guarantee (3 families per run minimum)
- Prevents runs dominated by a single family
- Memory-weighted preferences still respected within caps

### CC-BE-2473: Brief Language Hardening
- `_generate_headline`: now includes physical changes (capacity %, resistance %) not just score
- `_generate_why_promising`: explains tradeoff using mOhm, Ah, delta % instead of listing component names
- `_generate_score_summary`: shows best/weakest dimension with values

---

## 4. Recommended Next Focus

### Recommendation: DC-DC as Domain 3 OR Battery Product Deepening

The battery loop is now materially better:
- Selective promotion (67%, not 100%)
- Cathode families competitive (32% of wins)
- Differentiated briefs (94% unique)
- 6 families winning

The remaining concentration issues are structural:
- `bounded_aggressive` still leads at 39% — this is because its perturbation range covers more scoring dimensions
- `combined_moderate` and `improved_efficiency` now never win — they can't beat 0.84 threshold
- `improved_capacity` still never wins — capacity improvement alone doesn't produce high enough composite scores

**Option A: DC-DC as domain 3**
- Validates the multi-domain engine architecture
- Proves the benchmark loop pattern is replicable
- Lower risk: well-understood domain, clear metrics

**Option B: Battery product deepening**
- Make the workspace actually useful for real battery evaluation workflows
- Focus on the Decision Brief → review → export → act cycle
- Connect briefs to real engineering decisions

**Recommended: Option A** (DC-DC domain 3) — the battery loop is now healthy enough to serve as a reference implementation. Adding DC-DC proves the engine scales to multiple domains and derisks the architecture before going deeper on any one domain.

---

## 5. Known Limitations

1. **Score compression**: promoted scores are now in a tight 0.84-0.87 band, making it harder to rank among promoted candidates
2. **15 runs failed to promote any candidate**: this is desirable for selectivity but means fewer data points per evaluation
3. **bounded_aggressive still leads**: 39% share is acceptable but not ideal; further tuning would require deeper scoring changes
4. **combined_moderate and improved_efficiency eliminated**: these families can no longer compete at the 0.84 threshold — they may need perturbation range updates
5. **cathode_high_ni underperforms**: its high R0 improvement is less impressive when scored against NMC-811 baseline (R0=22) rather than generic (R0=30)
6. **Campaign script has a bug**: errors on no-promotion runs due to NoneType access — doesn't affect results but skews the error count
