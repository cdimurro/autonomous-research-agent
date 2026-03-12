# Phase 10C: A/B Results

## Trial Configuration

- 6+6 campaigns (6 current retrieval, 6 KG retrieval)
- Champion policy: evidence_diversity_v1
- Embedding: qwen3-embedding:4b (Regime 2)
- Generation: qwen3.5:9b-q4_K_M
- Profile: production_local clean-energy
- Total runtime: 7268s (~2h)

## Results

| Metric | Current Arm | KG Arm |
|--------|-------------|--------|
| Mean champion score | 0.8741 | 0.8092 |
| Score range | 0.861-0.891 | 0.799-0.839 |
| Approval rate | 100% | 0% (100% defer) |
| Mean finalists | 3.0 | 2.5 |
| Campaigns succeeded | 6/6 | 5/6 |

## Score Delta: -0.065

The KG arm produced candidates scoring ~6.5% lower on average. While the candidates are viable (0.79-0.84 range), they fall below the auto-approve threshold (0.85).

## Diversity Paradox

Phase 10B showed KG retrieval has 4x better source diversity at the evidence gathering level. However, this diversity advantage did not translate to better downstream candidate quality in the A/B trial. Possible explanations:

1. The scoring pipeline rewards evidence from high-confidence findings, which current retrieval provides
2. KG segments have systematically lower relevance scores
3. Evidence diversity may matter more at larger corpus sizes than tested

## Review Labels

- 22 total labels generated (12 current, 10 KG)
- Current arm: 12/12 approve (100%)
- KG arm: 0/10 approve, 10/10 defer (0%)
- No rejects in either arm
