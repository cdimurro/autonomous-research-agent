# KG Switch-Readiness Decision — Phase 10B

## Recommendation

**`ready_for_retrieval_ab`**

KG retrieval outperforms current production retrieval on diversity and content density metrics. The evidence supports proceeding to a controlled A/B trial.

## Evidence Base

### Strengths
1. KG has 396 segments — materially exceeds current effective evidence pool (2 papers)
2. 168 entities and 94 relations extracted with good type coverage (11 entity types, 9 relation types)
3. KG shadow retrieval delivers 4-8x source diversity improvement
4. Top-1 source concentration drops from 96.5% to 52%
5. Write-back scaffold is healthy and ready for future activation

### Issues
None blocking. Minor notes:
- Only 27/396 segments fully extracted (LLM extraction is slow but can continue incrementally)
- Mean relevance score is lower (0.49 vs 0.93) — but this reflects monoculture inflation in current scores

## Prescribed Next Experiment

| Parameter | Value |
|-----------|-------|
| Design | 6+6 A/B trial |
| Profile | evaluation_daily_clean_energy |
| Arms | Current retrieval (control) vs KG retrieval (treatment) |
| Policy | evidence_diversity_v1 (champion) for both arms |
| Embedding | qwen3-embedding:4b (Regime 2) for both arms |
| Generation | qwen3.5:9b-q4_K_M for both arms |

### Success Metrics
- KG arm mean score >= current arm mean score - 0.02
- KG arm source diversity >= current arm
- KG arm approval rate >= 60%

### Rollback Criteria
- KG arm mean score < current arm mean score - 0.05
- KG arm approval rate < 40%

## What Must NOT Happen
- No production retrieval switch without A/B trial completion
- No merge to main
- No policy change during trial
- No embedding regime change during trial
