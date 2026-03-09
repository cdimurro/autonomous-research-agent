# Review Cockpit

## Overview

The review cockpit produces a structured `ReviewDecisionPacket` for each candidate that reaches the review stage. It consolidates all relevant signals into a single, human-readable decision packet, reducing operator burden.

## ReviewDecisionPacket Contents

| Field | Description |
|-------|-------------|
| `candidate_summary` | One-paragraph summary of the hypothesis |
| `why_beat_challengers` | Why this candidate scored higher than alternatives |
| `posterior_confidence` | Bayesian posterior summary for the policy that generated it |
| `falsification_summary` | Structured risk assessment |
| `evidence_balance_summary` | Primary/secondary/bridge evidence breakdown |
| `novelty_neighbor_summary` | Nearest semantic neighbors and distances |
| `synthesis_fit_summary` | Cross-domain synthesis quality |
| `recommended_action` | APPROVE / DEFER / REJECT with rationale |
| `runner_up_comparison` | Comparison vs runner-up candidates (daily mode) |

## Recommended Action Logic

| Condition | Action |
|-----------|--------|
| final_score >= 0.75 AND falsification_passed | APPROVE |
| final_score >= 0.60 | DEFER (manual review) |
| final_score < 0.60 OR high falsification risk | REJECT |

## Text Output Example

```
═══════════════════════════════════════════════════
REVIEW DECISION PACKET
═══════════════════════════════════════════════════
Candidate: MXene-Reinforced Anodes for Perovskite Arrays
Run ID:    abc12345

SUMMARY
  Hypothesis: MXene Ti3C2Tx electrode materials applied as
  anode reinforcement in perovskite solar arrays improves
  corrosion resistance by 40% while maintaining >98% efficiency.

SCORES
  Final Score:    0.909
  Evidence:       0.875
  Synthesis Fit:  0.820

FALSIFICATION RISK: LOW
  Contradictions found: 0
  Missing evidence gaps: 0
  Assumption fragility: 0.82 (robust)
  Bridge weakness flags: none

POSTERIOR CONFIDENCE (draft_creation, policy=phase5_champion)
  Mean: 0.85, 95% CI: [0.72, 0.94], n=20 (low uncertainty)

NOVELTY NEIGHBORS
  Nearest: "MXene electrode corrosion..." (similarity: 0.71)
  Above threshold — genuinely novel

SYNTHESIS FIT
  Bridge: interfacial mechanics bridging energy+materials
  Evidence balance: 0.82 (balanced)
  Cross-domain fit score: 0.84

RECOMMENDED ACTION: APPROVE
  Rationale: Score 0.909 >= 0.75, falsification risk low,
             posterior confidence high.
═══════════════════════════════════════════════════
```

## CLI Usage

```bash
# Show review packet for a run
python -m breakthrough_engine cockpit show RUN_ID

# Show review packet for a candidate
python -m breakthrough_engine cockpit show --candidate CANDIDATE_ID
```

## Flask API

```
GET /cockpit/<run_id>      → HTML review decision packet
```

Minimal server-rendered HTML — no JavaScript framework.
