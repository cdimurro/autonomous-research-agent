# Phase 6 Daily Quality-First Search Ladder

## Overview

The daily search ladder is a 5-stage structured campaign that searches for the highest-quality candidate of the day. Unlike benchmark mode (fixed budget), production mode uses a much larger local compute budget and applies Thompson sampling for policy selection.

## Two Modes

### Benchmark Mode
- Fixed stage budgets
- Offline-safe (FakeCandidateGenerator or real)
- Used for policy comparison and regression testing

### Production Mode
- Wall-clock budget per stage (configurable, default 120 min total)
- Real Ollama LLM + embedding
- Quality-first (higher publication threshold: 0.70)

## The 5 Stages

### Stage 1: Broad Exploration
- Goal: Generate many candidates across diverse policies/domains
- Config: max_trials=3, min_score_to_advance=0.40, max_wall_clock=300s
- Abandon floor: 0.30 (if all candidates below this, abandon stage)
- Early stop: if one candidate's posterior dominates others by > 0.15
- Output: list of finalists with scores

### Stage 2: Shortlist
- Goal: Select top-K candidates for deeper evaluation
- Config: shortlist_size=3 (configurable)
- Method: rank_candidates() from scoring.py
- Output: shortlisted candidates

### Stage 3: Falsification
- Goal: Stress-test shortlisted candidates
- Config: max_trials=3, min_score_to_advance=0.50, max_wall_clock=120s
- Abandon floor: 0.40
- Method: FalsificationEngine.evaluate() for each candidate
- Output: candidates with falsification_passed=True

### Stage 4: Review Packet Preparation
- Goal: Build detailed decision packets for survivors
- Config: review_prep=True (can disable for speed)
- Method: ReviewCockpit.build_packet()
- Output: ReviewDecisionPackets

### Stage 5: Daily Champion Selection
- Goal: Select the single best candidate of the day
- Method: rank by (falsification_passed, final_score)
- Output: daily_champion candidate + runner-up comparison

## Stopping Rules (Per Stage)

Each stage checks in order:
1. `early_stop_if_posterior_dominates`: stop if top candidate's posterior mean > others + 0.15
2. `max_trials` reached: proceed to next stage with what we have
3. `max_wall_clock_seconds` reached: proceed with partial results
4. `abandon_floor`: if all candidates below floor, mark stage as ABANDONED

A stage result carries `stop_reason`:
- `"completed"` — all trials ran, all criteria checked
- `"early_stopped"` — posterior dominance detected
- `"budget_exhausted"` — max_trials or wall_clock reached
- `"abandoned"` — all candidates below abandon_floor

## Campaign Result

```python
DailyCampaignResult(
    campaign_id="...",
    mode="production",
    policy_used="phase5_champion",
    daily_champion_id="...",
    champion_selection_rationale="Score 0.909, falsification_passed, beat 2 runner-ups",
    ladder_stages=[LadderStageResult(...), ...],
    policy_trials_attempted=3,
    domain_pairs_tried=["clean-energy+materials"],
    bridge_mechanisms_tried=["electrocatalysts...", "electrode materials..."],
    total_candidates_generated=15,
    total_blocked=2,
    total_shortlisted=3,
    elapsed_seconds=245.3,
)
```

## CLI Usage

```bash
# Run benchmark mode (offline-safe)
python -m breakthrough_engine daily-search run --mode benchmark

# Run production mode (requires Ollama, 30-min budget)
python -m breakthrough_engine daily-search run --mode production --budget 30

# Run with specific policy
python -m breakthrough_engine daily-search run --policy POLICY_ID
```
