# KG Shadow Retrieval Results — Phase 10B

## The Monoculture Problem

Production evidence retrieval has a severe diversity bottleneck:

- **96.5%** of evidence items come from a single paper (arxiv:2402.11234)
- Only **2 unique source papers** across 200 evidence items
- Source type: 100% `finding` (no structural/graph evidence)
- This monoculture limits candidate hypothesis diversity

## KG Shadow Retrieval Performance

| Metric | Current (Production) | KG Shadow | Delta |
|--------|---------------------|-----------|-------|
| Unique sources (30 items) | 1 | 8 | +7 |
| Top-1 concentration (30 items) | 100% | 26.7% | -73.3pp |
| Unique sources (200 items) | 2 | 8 | +6 |
| Top-1 concentration (200 items) | 96.5% | 52% | -44.5pp |
| Mean relevance | 0.93 | 0.49 | -0.44 |
| Mean quote length | 103 chars | 200 chars | +97 |
| Source overlap | 0% | | |

**Verdict: `shadow_better`**

## Interpretation

- **Diversity is dramatically better**: 4-8x more unique sources
- **Relevance is lower**: 0.49 vs 0.93 — expected since current retrieval returns the same highly-scored paper repeatedly. High relevance from monoculture is a false signal.
- **Content density is higher**: Mean quote length 200 vs 103 chars — KG segments contain more material per item
- **Zero overlap**: KG retrieval surfaces entirely different evidence, addressing the monoculture directly

## Campaign-Level Impact

Existing production candidates already achieve high quality (mean final score 0.9465), but:
- High novelty scores (0.998) may partly reflect echo-chamber evidence
- KG-backed candidates would draw on more diverse scientific grounding
- Diversity improvement is the primary expected benefit

## Artifacts

- `runtime/phase10b/retrieval_comparison/retrieval_comparison.json`
- `runtime/phase10b/retrieval_comparison/diversity_summary.json`
- `runtime/phase10b/retrieval_comparison/evidence_items_current.csv`
- `runtime/phase10b/retrieval_comparison/evidence_items_kg.csv`
- `runtime/phase10b/campaign_comparison/campaign_comparison.json`
