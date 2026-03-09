# Phase 7B Evaluation Pack Report

## Evaluation Packs Exported

### Pack 1: b87513b86b6f4b1f (Phase 7A overnight — retroactive)

| Field | Value |
|-------|-------|
| Campaign ID | b87513b86b6f4b1f |
| Profile | overnight_clean_energy (overnight) |
| Status | completed_with_draft |
| Runtime | 2211s (36.9 min) |
| Candidates generated | 80 |
| Finalists | 5 |
| Champion | Hybrid Offshore TPV-Wind Systems for Nighttime Grid Stabilization |
| Champion score | 0.947 |
| Embedding provider | MockEmbeddingProvider (Phase 7A — no real embeddings) |
| Policy | phase5_champion |
| Pack location | runtime/evaluation_packs/b87513b86b6f4b1f/ |

**Top 5 Finalists:**

| Rank | Score | Title | Falsif Risk |
|------|-------|-------|-------------|
| 1 | 0.947 | Hybrid Offshore TPV-Wind Systems for Nighttime Grid Stabilization **[CHAMPION]** | medium |
| 2 | 0.947 | Sulfide-Electrolyte Batteries for Offshore Subsea Energy Storage | medium |
| 3 | 0.947 | Trap-Passivated Thermal Emission Mitigation | medium |
| 4 | 0.937 | Cross-Coupled Thermal-Electrical Recycling in Perovskite Tandems | medium |
| 5 | 0.934 | Ammonia Cracking Catalysts for Carbon-Free Offshore Shipping Fuel | medium |

**Tiebreak**: 3-way tie at 0.947. Champion selected by simulation_readiness_score (1.0 vs 1.0 vs 0.9).

### Pack 2: b80c979d75144fb8 (Phase 7B smoke campaign)

| Field | Value |
|-------|-------|
| Campaign ID | b80c979d75144fb8 |
| Profile | smoke_10m (smoke) |
| Status | completed_with_draft |
| Runtime | 554s (9.2 min) |
| Embedding provider | OllamaEmbeddingProvider(nomic-embed-text) |
| Champion | Thermally Activated Argyrodite Coatings for Blade De-Icing |
| Pack location | runtime/evaluation_packs/b80c979d75144fb8/ |

### Pack 3: f01a0a7c72304481 (Phase 7B overnight — in progress)

| Field | Value |
|-------|-------|
| Campaign ID | f01a0a7c72304481 |
| Profile | overnight_clean_energy (overnight) |
| Status | running |
| Started | 2026-03-09T05:11:06Z |
| Embedding provider | OllamaEmbeddingProvider(nomic-embed-text) |
| PID | 35157 |
| Log | nohup_campaign_7b.log |
| Pack location | runtime/evaluation_packs/f01a0a7c72304481/ (after completion) |

Export after completion:
```bash
BT_EMBEDDING_MODEL=nomic-embed-text .venv/bin/python -m breakthrough_engine evaluation-pack export f01a0a7c72304481
```

## Evaluation Pack File Structure

```
runtime/evaluation_packs/<campaign_id>/
├── evaluation_pack.json    # Complete structured data (schema v001)
├── evaluation_pack.md      # Human-readable markdown summary
├── candidates.csv          # All candidates with scores
└── finalists.csv           # Finalist candidates with full text
```

## Notable Contents per Pack

### evaluation_pack.json
- Full candidate records with all score dimensions
- Falsification risk, passed flag, assumption fragility
- Tiebreak rationale with ranked finalists
- Stage event timings
- Preflight health (15 checks, readiness score)
- Bayesian posteriors snapshot
- Which embedding provider was used
- Campaign config snapshot
- Model info (generation model, embedding provider)

### candidates.csv
- 1 row per candidate
- All 6 score dimensions per row
- Falsification risk + passed flag
- Evidence references

### finalists.csv
- Finalist rows only + statement + mechanism (full text)
- Suitable for spreadsheet analysis

## Designed for ChatGPT Analysis

The evaluation_pack.json is structured to allow prompts like:
- "Compare the top 5 finalists and explain the tiebreak"
- "What are the highest-risk assumptions in the champion?"
- "Which evidence items were most relied upon?"
- "How do the scores break down by scientific domain?"
- "Was this campaign using real or mock embeddings, and what does that mean for novelty detection quality?"
