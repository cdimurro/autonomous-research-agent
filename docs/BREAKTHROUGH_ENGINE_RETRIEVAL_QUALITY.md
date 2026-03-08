# Breakthrough Engine - Retrieval Quality (Phase 4B)

## Overview

Phase 4B added layered retrieval ranking and improved evidence-to-candidate linking.

## Query Construction

`build_retrieval_query()` in `retrieval.py` builds improved search queries by combining:
- Domain terms (e.g., "clean energy")
- Mechanism keywords (top 6 from candidate mechanism text)
- Program goal terms (top 4)
- Prior-art keywords (optional, up to 3)

Deduplicates tokens and caps at 20 words for API compatibility.

## Evidence Ranking

`rank_evidence()` scores evidence items using a layered approach:

| Layer | Weight | Signal |
|-------|--------|--------|
| API relevance | 0.35 | Original relevance score from OpenAlex/Crossref |
| Domain keyword overlap | 0.30 | How many domain keywords appear in title/abstract |
| Mechanism keyword overlap | 0.20 | How many candidate mechanism keywords match |
| Recency bonus | 0.10 | Papers from 2024+ get a bonus |
| Baseline | 0.075 | All items get a small baseline |

Each item receives a `rank_explanation` string showing the layer scores.

## Evidence Linking Improvement

### Before (Phase 4A)
- LLM-generated `evidence_refs` rarely matched actual evidence item IDs
- Fallback: attach first 2 evidence items regardless of relevance

### After (Phase 4B)
- First attempt: direct ID matching from `evidence_refs`
- If no match: use `rank_evidence()` to select the top items by relevance
- Evidence rankings are persisted in `bt_evidence_rankings` for auditability
- Candidate `evidence_refs` are updated to reflect actual linked items

## Persistence

Evidence rankings are stored in `bt_evidence_rankings` (v003 migration):
- `candidate_id`, `evidence_id`, `composite_score`, `rank_explanation`

## Testing

Tests in `test_phase4b.py::TestRetrievalRanking`:
- Ranking sorts by composite score
- Ranking produces explanations
- Query construction includes relevant terms
- Query deduplicates words
- Domain keywords boost ranking
- Empty evidence returns empty
