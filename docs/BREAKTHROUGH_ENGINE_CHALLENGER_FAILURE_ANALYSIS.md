# Challenger Failure Analysis: synthesis_focus_v1

**Trial ID**: phase9b_ab_trial
**Trial Date**: 2026-03-11
**Embedding Regime**: Regime 2 (qwen3-embedding:4b, 2560d)
**Status**: FROZEN — trusted negative result

---

## 1. Trial Summary

| Metric | Champion (phase5_champion) | Challenger (synthesis_focus_v1) | Delta |
|--------|---------------------------|--------------------------------|-------|
| Mean champion score | 0.90804 | 0.87789 | **-0.03015** |
| Approval rate | 75% (9/12) | 25% (3/12) | **-50.0pp** |
| Novelty confidence | 0.783 | 0.713 | **-0.070** |
| Technical plausibility | 0.763 | 0.694 | **-0.069** |
| Commercialization relevance | 0.710 | 0.633 | **-0.077** |
| Reject rate | 0% (0/12) | 17% (2/12) | **+17pp** |
| Defer rate | 25% (3/12) | 58% (7/12) | **+33pp** |

**Verdict: PROMOTION_NOT_RECOMMENDED** — all four promotion gates failed. Challenger strictly dominated by champion on every measured dimension.

---

## 2. Challenger Configuration

```json
{
  "name": "synthesis_focus_v1",
  "generation_prompt_variant": "synthesis_focus",
  "scoring_weights": {
    "novelty": 0.18,       // -10% vs champion default 0.20
    "plausibility": 0.25,  // +25% vs champion default 0.20
    "impact": 0.20,
    "evidence_strength": 0.20,
    "simulation_readiness": 0.12, // +20% vs champion default 0.10
    "inverse_validation_cost": 0.05 // -50% vs champion default 0.10
  }
}
```

**Hypothesis** (stated): Higher plausibility/simulation_readiness scoring weights produce candidates with better reviewer technical plausibility scores and higher approval rates.

---

## 3. Structured Diagnosis

### 3.1 Score Delta

- Champion: 0.90804 mean (tight range: 0.883–0.921)
- Challenger: 0.87789 mean (wider range: 0.850–0.911)
- Delta: **-0.03015** — exceeds the -0.03 threshold, barely

The score drop is partly a mechanical artifact: the challenger weights down novelty (0.18 vs 0.20), which reduces the composite score for any candidate with the same underlying novelty quality.

### 3.2 Approval Rate Delta

- Champion: 75% (9 approve, 0 reject, 3 defer)
- Challenger: 25% (3 approve, 2 reject, 7 defer)
- Delta: **-50 percentage points**

This is the most damaging failure. The challenger produced substantially more deferred and rejected candidates. Reviewer patterns suggest:
- Frequent "defer" on concepts that lacked novelty framing or mechanistic specificity
- Two explicit "reject" decisions (campaign 297: radiative-PCM concept — "concept is weakly specified and evidence strength is insufficient")
- Approvals only on the strongest challenger campaigns (ef9aade: ammonia cracking dual-use, "creative dual-use synthesis concept")

### 3.3 Novelty Confidence Delta

- Champion: 0.783 mean
- Challenger: 0.713 mean
- Delta: **-0.070**

This was expected from the design: the synthesis_focus prompt is intended to generate more "practical" (less creative) candidates. However, the hypothesis was that plausibility gains would compensate. They did not.

### 3.4 Technical Plausibility Delta

- Champion: 0.763 mean
- Challenger: 0.694 mean
- Delta: **-0.069**

**Critical failure of hypothesis.** The challenger was designed to improve technical plausibility. Instead, it declined. This is the central diagnostic finding: upweighting plausibility in the scoring function does NOT cause reviewers to rate plausibility higher. The scoring weight is a measurement/prioritization tool, not a quality lever.

### 3.5 Commercialization Relevance Delta

- Champion: 0.710 mean
- Challenger: 0.633 mean
- Delta: **-0.077**

Largest absolute decline. The synthesis_focus prompt's emphasis on simulation-readiness pulled candidates toward abstract simulation scenarios rather than commercially grounded engineering problems.

### 3.6 Evidence Balance

No evidence that the evidence balance was the primary driver. The evidence ranking weights were null in synthesis_focus_v1 (program defaults used), so evidence input to both arms was drawn from the same distribution. The key difference was in how candidates were generated FROM that evidence.

### 3.7 Finalist Composition

The champion arm consistently produced candidates across diverse sub-domains (seawater electrolysis, ammonia cracking, solid-state batteries, MOFs, perovskites, bio-derived materials). The challenger arm showed:
- Campaign 297 (worst): both champion and runner-up rejected — radiative cooling + PCM, weakly specified, no cross-domain bridge
- Campaign 775 (weakest challenger): MOF filter + NiFe-LDH — both deferred, concepts not differentiated
- Only campaign ef9aade produced strong approved champion (ammonia cracking CO2 heat sink)

---

## 4. Root Cause Analysis

### Intended Effect
Upweight plausibility and simulation_readiness in scoring → select candidates that score higher on these dimensions → reviewers see more technically concrete proposals → approval rate improves.

### Actual Effect
Scoring weight changes select candidates with higher plausibility/simulation_readiness SCORES but lower novelty SCORES. The synthesis_focus prompt generates candidates that are incremental variants of known techniques rather than novel cross-domain bridges. Reviewers detect the incremental nature and defer/reject.

### Likely Cause

**Mechanism coupling error.** The design treated scoring weights as a quality lever but they are a selection lever. By upweighting plausibility, the system selected candidates that appeared more plausible in the auto-scorer's model — but plausibility in the auto-scorer reflects known-technique familiarity, not reviewer-assessed technical correctness. Meanwhile, the synthesis_focus prompt reduced novelty at the generation stage, creating a double penalty:
1. Fewer novel hypotheses generated (prompt effect)
2. Novelty penalized in final ranking (weight effect)

The hypothesis assumed a clean trade-off: less novelty, more plausibility, net positive approval. The actual dynamic is: less novelty + unchanged plausibility quality = lower approval rate, because reviewers reward novelty above a plausibility floor, not plausibility above a novelty floor.

---

## 5. Recurring Flaw Patterns From Reviewer Notes

From review_labels.csv, challenger arm patterns:

| Pattern | Frequency | Example note |
|---------|-----------|-------------|
| Concept underspecified / needs mechanistic grounding | 4/12 | "needs stronger mechanistic grounding before approval" |
| Novelty framing weak / incremental | 3/12 | "novelty framing needs sharpening", "limited novelty" |
| Differentiation from prior art unclear | 2/12 | "proposal needs more specific differentiation" |
| Physical underspecification | 2/12 | "concept is weakly specified and evidence strength is insufficient" |
| Strong approval (passes all criteria) | 3/12 | ammonia cracking, MOF/ammonia dual-use |

The pattern is clear: the synthesis_focus challenger produced more often proposals that reviewers found incremental, underspecified, or lacking cross-domain novelty.

---

## 6. Key Lesson

**Scoring weights are selection tools, not quality levers.** Upweighting a dimension selects for candidates that score higher on that dimension in the existing scorer — it does not cause the LLM to generate candidates of objectively higher quality on that dimension.

To improve reviewer-assessed technical plausibility, the intervention must occur earlier in the pipeline:
- At the evidence level (better evidence → better grounded candidates), or
- At the prompt level (explicitly scaffold plausibility constraints in generation), or
- At the novelty-plausibility balance level (preserve novelty while improving specificity)

The synthesis_focus prompt failed because it is not a targeted plausibility intervention — it is a synthesis-framing intervention that happens to suppress novelty as a side effect.

---

## 7. Artifact Locations

| Artifact | Path |
|---------|------|
| Arm summary (frozen) | `runtime/challenger_trials/phase9b_ab_trial/arm_summary.json` |
| Posterior summary | `runtime/challenger_trials/phase9b_ab_trial/posterior_summary.json` |
| Challenger vs champion | `runtime/challenger_trials/phase9b_ab_trial/challenger_vs_champion_summary.json` |
| Review labels | `runtime/challenger_trials/phase9b_ab_trial/review_labels.csv` |
| Policy config | `config/policies/synthesis_focus_v1.json` |
| Promotion decision | `docs/BREAKTHROUGH_ENGINE_PHASE9B_REVISED_PROMOTION_DECISION.md` |

---

## 8. Disposition of synthesis_focus_v1

Status: **RETIRED_FAILED** — preserved as a learning artifact.
- Do not re-run this challenger.
- Policy config (`config/policies/synthesis_focus_v1.json`) retained for audit trail.
- Artifacts in `runtime/challenger_trials/phase9b_ab_trial/` are immutable.
- Next challenger must address the identified failure pattern with a different mechanism.
