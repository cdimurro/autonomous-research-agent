# Bayesian Evaluation Engine

## Overview

The Bayesian evaluation layer tracks posterior beliefs over key quality signals for each policy/domain pair. It replaces raw averages with principled uncertainty tracking and enables Thompson sampling and UCB-based policy selection.

## Observation Units

Every metric has an explicit observation unit. Posteriors update at the correct granularity.

| Metric | Unit | Distribution | Update Rule |
|--------|------|-------------|------------|
| `novelty_pass` | candidate-level | Beta-Binomial | alpha += success, beta += (1-success) |
| `synthesis_fit_pass` | candidate-level | Beta-Binomial | same |
| `review_worthy` | candidate-level (score >= 0.60) | Beta-Binomial | same |
| `draft_creation` | run-level | Beta-Binomial | same |
| `review_approval` | draft-level | Beta-Binomial | same |
| `final_score` | candidate-level continuous | Normal (Welford's) | online mean/variance |
| `evidence_balance` | candidate-level continuous | Normal (Welford's) | same |
| `synthesis_fit_score` | candidate-level continuous | Normal (Welford's) | same |

## Prior

- Binary metrics: Beta(1, 1) = uniform prior (zero observations assumed)
- Continuous metrics: mu=0.0, M2=0.0, n=0

## Posterior State

```python
PosteriorState(
    policy_id="phase5_champion",
    domain="clean-energy",
    metric_name="novelty_pass",
    observation_unit="candidate",
    distribution_type="beta_binomial",
    alpha=8.0,   # 7 successes + 1 prior
    beta=2.0,    # 1 failure + 1 prior
    n=0,         # not used for beta-binomial
    last_updated="2026-03-08T12:00:00Z",
    update_history=[...]  # last 50 updates kept for audit
)
```

## Posterior Summary

For Beta(alpha, beta):
- Mean: alpha / (alpha + beta)
- Variance: alpha*beta / ((alpha+beta)^2 * (alpha+beta+1))
- 95% CI: approximate (mean ± 2*sqrt(variance))
- Sample size: alpha + beta - 2 (number of observations)
- Uncertainty label: "high" (n<5), "medium" (5<=n<20), "low" (n>=20)

## Thompson Sampling

For policy selection in daily search:
1. For each policy, sample once from its posterior
2. Rank policies by sample value descending
3. Select top-ranked policy for next trial

```python
# Binary: sample from Beta(alpha, beta)
import random
sample = random.betavariate(state.alpha, state.beta)

# Continuous: sample from Normal(mu, sigma)
import random
sigma = math.sqrt(state.M2 / max(state.n - 1, 1))
sample = random.gauss(state.mu, sigma)
```

## UCB Selection

UCB = mean + c * sqrt(variance / max(n, 1))

Where c=2.0 by default (exploration parameter).

## Persistence

Posteriors are stored in `bt_bayesian_posteriors`. The `update_history_json` column stores the last 50 updates in append-only fashion for audit and debugging.

## Explainability

Each update emits an explanation string:
```
Prior: alpha=1.0 beta=1.0 → mean=0.500 (high uncertainty, n=0)
Observation: success=True
Posterior: alpha=2.0 beta=1.0 → mean=0.667 (high uncertainty, n=1)
Change: +0.167 in mean, uncertainty still high
```

## Usage

```python
evaluator = BayesianEvaluator()

# Update after a candidate passes novelty
state = evaluator.load_posteriors(repo, policy_id, domain).get("novelty_pass")
if state is None:
    state = evaluator.new_state(policy_id, domain, "novelty_pass")
state = evaluator.update_binary(state, success=True)
evaluator.persist_posterior(repo, state)

# Rank policies for next trial
ranked = evaluator.rank_policies_thompson({
    "policy_A": states_A,
    "policy_B": states_B,
}, metric="draft_creation")
```
