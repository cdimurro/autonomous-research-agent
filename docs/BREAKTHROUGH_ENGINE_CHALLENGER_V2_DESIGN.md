# Challenger V2 Design: evidence_diversity_v1

**Phase**: 9C/9D
**Status**: PROMOTION_RECOMMENDED — phase9d_ab_trial COMPLETE
**Predecessor**: synthesis_focus_v1 (RETIRED_FAILED — see BREAKTHROUGH_ENGINE_CHALLENGER_FAILURE_ANALYSIS.md)
**Champion baseline**: phase5_champion

---

## 1. Design Rationale

### What synthesis_focus_v1 taught us

The previous challenger failed because it intervened at the wrong point in the pipeline:
- Changed the generation prompt → suppressed novelty
- Upweighted plausibility in scoring → rewarded incremental candidates
- Result: lower novelty, lower plausibility, worse approval rates

The key lesson: **scoring weights are selection tools, not quality levers**. To improve output quality, intervene earlier — at the evidence quality/selection stage.

### Hypothesis for evidence_diversity_v1

If candidates are generated from better mechanism-aligned evidence, they will contain stronger mechanistic specificity and cross-domain grounding, which should:
1. Preserve or improve novelty (better evidence → richer cross-domain synthesis)
2. Improve reviewer-assessed plausibility (mechanism-aligned evidence → more concrete candidates)
3. Avoid the novelty-plausibility trade-off that destroyed synthesis_focus_v1

---

## 2. Configuration Diff

### Surface Changed: `evidence_ranking_weights` (single surface)

| Weight | Champion default | evidence_diversity_v1 | Change |
|--------|-----------------|----------------------|--------|
| api_relevance | 0.35 | 0.20 | -43% |
| domain_overlap | 0.30 | 0.30 | unchanged |
| mechanism_overlap | 0.20 | 0.35 | +75% |
| baseline | 0.15 | 0.15 | unchanged |

### All other surfaces: unchanged from champion

```json
{
  "name": "evidence_diversity_v1",
  "generation_prompt_variant": "standard",    // same as champion
  "scoring_weights": null,                    // champion defaults
  "diversity_steering_variant": "standard",   // same as champion
  "sub_domain_rotation_policy": "auto",       // same as champion
  "evidence_ranking_weights": {
    "api_relevance": 0.20,
    "domain_overlap": 0.30,
    "mechanism_overlap": 0.35,
    "baseline": 0.15
  }
}
```

---

## 3. Mechanism of Action

The `rank_evidence` function scores each evidence item across four layers:
1. **api_relevance** — score returned by the retrieval API (OpenAlex, Semantic Scholar)
2. **domain_overlap** — keyword overlap with the research domain
3. **mechanism_overlap** — keyword overlap with the current mechanism context
4. **baseline** — flat baseline score applied uniformly

**Champion behavior**: api_relevance dominates (0.35), meaning the most API-relevant papers surface first regardless of mechanistic fit to the current hypothesis context.

**Challenger behavior**: mechanism_overlap dominates (0.35), meaning papers that most closely align with the current mechanism context surface first. This should provide candidates with:
- Stronger mechanistic grounding in the evidence
- More specific cross-domain connections (mechanism keywords match actual hypothesis mechanisms)
- Less dependence on generic domain relevance from external APIs

The generation prompt is unchanged (standard), so novelty is not suppressed at the generation stage.

---

## 4. Why This Addresses synthesis_focus_v1 Failures

| synthesis_focus_v1 failure | evidence_diversity_v1 response |
|---------------------------|-------------------------------|
| Prompt suppressed novelty | Prompt unchanged (standard) — novelty preserved |
| Scoring weights penalized novelty | Scoring weights unchanged — no novelty penalty |
| Plausibility improved in scorer but not in reviewer | Evidence quality improved → concrete mechanisms → reviewer plausibility improves |
| Defers/rejects due to underspecification | Mechanism-aligned evidence gives generator more specific inputs |
| No change in evidence selection | Evidence ranking now mechanism-weighted |

---

## 5. Expected Outcomes

| Metric | Expected direction | Confidence |
|--------|-------------------|------------|
| Mean champion score | neutral to slight improvement | moderate |
| Approval rate | neutral to improvement vs champion | moderate |
| Novelty confidence | neutral (prompt unchanged) | high |
| Technical plausibility | neutral to improvement | moderate |
| Commercialization relevance | neutral | low |

**Conservative expectation**: No regression. The intervention is mild (single surface, no prompt change), so we do not expect dramatic improvement. Success means no regression combined with evidence of improved mechanistic specificity in candidates.

**Promotion threshold**: All four reviewed gates must pass:
- score_delta ≥ -0.03 (no regression)
- approval_rate_delta ≥ -0.05 (no approval collapse)
- novelty_confidence_delta ≥ -0.05 (no novelty loss)
- technical_plausibility_delta ≥ -0.05 (no plausibility loss)

---

## 6. What Could Go Wrong

1. **api_relevance reduction** may surface less relevant evidence from marginal papers. Mitigation: mechanism_overlap compensates by selecting for mechanistic fit.
2. **mechanism_overlap** depends on quality of the mechanism context string. For early campaigns without a strong mechanism context, the effect may be muted.
3. **No significant change** if most evidence items score similarly on both api_relevance and mechanism_overlap.

---

## 7. Policy File Location

`config/policies/evidence_diversity_v1.json`

---

## 8. A/B Trial Plan

When ready (after collecting new baseline runs under champion):

- **Trial ID**: `phase9d_ab_trial`
- **Profile**: `eval_clean_energy_30m`
- **Arms**: 6 champion + 6 challenger (minimum)
- **Labels**: 2 per campaign (champion + runner-up), 24 minimum
- **Regime**: Regime 2 (qwen3-embedding:4b) — mandatory
- **Promotion**: manual only, all gates must pass

**Commands**:
```bash
# Champion arm
python -m breakthrough_engine ds run eval_clean_energy_30m

# Challenger arm
python -m breakthrough_engine ds run eval_clean_energy_30m --policy evidence_diversity_v1
```

---

## 9. Archiving synthesis_focus_v1

`synthesis_focus_v1` is retired as a failed challenger:
- Config file retained at `config/policies/synthesis_focus_v1.json` (read-only reference)
- All trial artifacts retained in `runtime/challenger_trials/phase9b_ab_trial/`
- Policy is NOT re-registered for any future runs
- Future challengers must justify their design against this negative result
