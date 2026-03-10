"""Bayesian evaluation engine for the Breakthrough Engine Phase 6.

Tracks posterior beliefs over key quality signals per policy/domain pair.
Uses Beta-Binomial for binary signals and Normal approximation (Welford's
online algorithm) for continuous signals.

Key design decision: Every metric has an explicit observation unit.
Posteriors update at the CORRECT granularity — not with run-level rates
when the unit is candidate-level.

Supported policy selection methods:
- Thompson sampling (default)
- UCB (Upper Confidence Bound)
"""

from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Binary metrics (Beta-Binomial posterior)
BINARY_METRICS: dict[str, str] = {
    "novelty_pass": "candidate",
    "synthesis_fit_pass": "candidate",
    "review_worthy": "candidate",
    "draft_creation": "run",
    "review_approval": "draft",
}

# Continuous metrics (Normal approximation via Welford's)
CONTINUOUS_METRICS: dict[str, str] = {
    "final_score": "candidate",
    "evidence_balance": "candidate",
    "synthesis_fit_score": "candidate",
}

# Phase 8: Reviewed metrics — posteriors from human review labels
# Binary: Beta(2, 2) prior (weakly informative, 50% with 4 pseudo-observations)
REVIEWED_BINARY_METRICS: dict[str, str] = {
    "review_label_approval": "label",    # P(approve) per labeled candidate
}

# Continuous: Normal(0.5, 0.25) prior — centered at neutral
REVIEWED_CONTINUOUS_METRICS: dict[str, str] = {
    "review_novelty_confidence": "label",
    "review_technical_plausibility": "label",
    "review_commercialization_relevance": "label",
}

# Prior parameters for reviewed metrics (weakly informative)
REVIEWED_BINARY_PRIOR = {"alpha": 2.0, "beta": 2.0}        # Beta(2,2): 50% with 4 pseudo-obs
REVIEWED_CONTINUOUS_PRIOR = {"mu": 0.5, "M2": 0.0, "n": 0}  # Starts at N(0.5, ?) uninformative

# Uncertainty labels by sample count
def _uncertainty_label(n: int) -> str:
    if n < 5:
        return "high"
    elif n < 20:
        return "medium"
    return "low"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Max update history entries to keep per posterior (for audit)
MAX_HISTORY_ENTRIES = 50


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PosteriorState:
    """Current posterior belief for one (policy, domain, metric) triple."""
    policy_id: str
    domain: str
    metric_name: str
    observation_unit: str     # "candidate" | "run" | "draft"
    distribution_type: str    # "beta_binomial" | "normal_approx"

    # Beta-Binomial params
    # alpha-1 = success count, beta-1 = failure count
    # prior is Beta(1,1) = uniform
    alpha: float = 1.0
    beta: float = 1.0

    # Normal approximation params (Welford's online algorithm)
    mu: float = 0.0
    M2: float = 0.0    # sum of squared deviations (for variance computation)
    n: int = 0

    last_updated: str = ""
    update_history: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "domain": self.domain,
            "metric_name": self.metric_name,
            "observation_unit": self.observation_unit,
            "distribution_type": self.distribution_type,
            "alpha": self.alpha,
            "beta": self.beta,
            "mu": self.mu,
            "M2": self.M2,
            "n": self.n,
            "last_updated": self.last_updated,
            "update_history": self.update_history,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PosteriorState":
        return cls(
            policy_id=d["policy_id"],
            domain=d["domain"],
            metric_name=d["metric_name"],
            observation_unit=d.get("observation_unit", "candidate"),
            distribution_type=d.get("distribution_type", "beta_binomial"),
            alpha=d.get("alpha", 1.0),
            beta=d.get("beta", 1.0),
            mu=d.get("mu", 0.0),
            M2=d.get("M2", 0.0),
            n=d.get("n", 0),
            last_updated=d.get("last_updated", ""),
            update_history=d.get("update_history", []),
        )


@dataclass
class PosteriorSummary:
    """Human-readable summary of a posterior state."""
    mean: float
    variance: float
    ci_lower: float      # approximate 95% lower bound
    ci_upper: float      # approximate 95% upper bound
    sample_size: int     # number of observations (excludes prior pseudo-counts)
    uncertainty_label: str  # "high" | "medium" | "low"
    metric_name: str = ""
    distribution_type: str = ""

    def to_dict(self) -> dict:
        return {
            "mean": round(self.mean, 4),
            "variance": round(self.variance, 6),
            "ci_lower": round(self.ci_lower, 4),
            "ci_upper": round(self.ci_upper, 4),
            "sample_size": self.sample_size,
            "uncertainty_label": self.uncertainty_label,
            "metric_name": self.metric_name,
            "distribution_type": self.distribution_type,
        }

    def format(self) -> str:
        return (
            f"{self.metric_name}: mean={self.mean:.3f} "
            f"95%CI=[{self.ci_lower:.3f},{self.ci_upper:.3f}] "
            f"n={self.sample_size} ({self.uncertainty_label} uncertainty)"
        )


# ---------------------------------------------------------------------------
# Bayesian Evaluator
# ---------------------------------------------------------------------------

class BayesianEvaluator:
    """Manages posterior states and policy selection via Thompson sampling / UCB."""

    # ---------------------
    # State creation
    # ---------------------

    def new_state(
        self,
        policy_id: str,
        domain: str,
        metric_name: str,
    ) -> PosteriorState:
        """Create a new uninformative prior state for a metric."""
        if metric_name in BINARY_METRICS:
            return PosteriorState(
                policy_id=policy_id,
                domain=domain,
                metric_name=metric_name,
                observation_unit=BINARY_METRICS[metric_name],
                distribution_type="beta_binomial",
                alpha=1.0,
                beta=1.0,
            )
        elif metric_name in CONTINUOUS_METRICS:
            return PosteriorState(
                policy_id=policy_id,
                domain=domain,
                metric_name=metric_name,
                observation_unit=CONTINUOUS_METRICS[metric_name],
                distribution_type="normal_approx",
                mu=0.0,
                M2=0.0,
                n=0,
            )
        else:
            raise ValueError(f"Unknown metric: {metric_name}")

    # ---------------------
    # Posterior updates
    # ---------------------

    def update_binary(self, state: PosteriorState, success: bool) -> PosteriorState:
        """Bayesian update for a binary observation (Beta-Binomial)."""
        if state.distribution_type != "beta_binomial":
            raise ValueError(f"Expected beta_binomial, got {state.distribution_type}")

        old_mean = self._beta_mean(state.alpha, state.beta)
        old_n = int(state.alpha + state.beta - 2)

        new_state = PosteriorState(
            policy_id=state.policy_id,
            domain=state.domain,
            metric_name=state.metric_name,
            observation_unit=state.observation_unit,
            distribution_type="beta_binomial",
            alpha=state.alpha + (1 if success else 0),
            beta=state.beta + (0 if success else 1),
            mu=state.mu,
            M2=state.M2,
            n=state.n,
            last_updated=_utcnow(),
            update_history=list(state.update_history),
        )

        new_mean = self._beta_mean(new_state.alpha, new_state.beta)
        explanation = self.explain_update(
            old_state=state,
            new_state=new_state,
            outcome=1.0 if success else 0.0,
        )
        new_state.update_history.append({
            "observation": int(success),
            "old_mean": round(old_mean, 4),
            "new_mean": round(new_mean, 4),
            "n_before": old_n,
            "ts": new_state.last_updated,
        })
        # Keep history bounded
        if len(new_state.update_history) > MAX_HISTORY_ENTRIES:
            new_state.update_history = new_state.update_history[-MAX_HISTORY_ENTRIES:]

        logger.debug("Posterior update %s: %s → mean %.3f", state.metric_name, explanation, new_mean)
        return new_state

    def update_continuous(self, state: PosteriorState, value: float) -> PosteriorState:
        """Bayesian update for a continuous observation (Welford's online algorithm)."""
        if state.distribution_type != "normal_approx":
            raise ValueError(f"Expected normal_approx, got {state.distribution_type}")

        new_n = state.n + 1
        delta = value - state.mu
        new_mu = state.mu + delta / new_n
        delta2 = value - new_mu
        new_M2 = state.M2 + delta * delta2

        new_state = PosteriorState(
            policy_id=state.policy_id,
            domain=state.domain,
            metric_name=state.metric_name,
            observation_unit=state.observation_unit,
            distribution_type="normal_approx",
            alpha=state.alpha,
            beta=state.beta,
            mu=new_mu,
            M2=new_M2,
            n=new_n,
            last_updated=_utcnow(),
            update_history=list(state.update_history),
        )
        new_state.update_history.append({
            "observation": round(value, 4),
            "old_mean": round(state.mu, 4),
            "new_mean": round(new_mu, 4),
            "n_before": state.n,
            "ts": new_state.last_updated,
        })
        if len(new_state.update_history) > MAX_HISTORY_ENTRIES:
            new_state.update_history = new_state.update_history[-MAX_HISTORY_ENTRIES:]

        return new_state

    # ---------------------
    # Posterior summaries
    # ---------------------

    def get_posterior_summary(self, state: PosteriorState) -> PosteriorSummary:
        """Compute a human-readable summary of the posterior."""
        if state.distribution_type == "beta_binomial":
            mean = self._beta_mean(state.alpha, state.beta)
            variance = self._beta_variance(state.alpha, state.beta)
            n = int(state.alpha + state.beta - 2)
            ci_half = 1.96 * math.sqrt(variance)
        else:
            mean = state.mu
            if state.n <= 1:
                variance = 0.25  # uninformative default
            else:
                variance = state.M2 / (state.n - 1)
            n = state.n
            ci_half = 1.96 * math.sqrt(variance / max(state.n, 1))

        return PosteriorSummary(
            mean=mean,
            variance=variance,
            ci_lower=max(0.0, mean - ci_half),
            ci_upper=min(1.0, mean + ci_half),
            sample_size=n,
            uncertainty_label=_uncertainty_label(n),
            metric_name=state.metric_name,
            distribution_type=state.distribution_type,
        )

    # ---------------------
    # Thompson sampling
    # ---------------------

    def thompson_sample(self, state: PosteriorState) -> float:
        """Draw one sample from the posterior."""
        if state.distribution_type == "beta_binomial":
            return random.betavariate(state.alpha, state.beta)
        else:
            if state.n <= 1:
                sigma = 0.5
            else:
                sigma = math.sqrt(state.M2 / (state.n - 1))
            # Clamp to [0, 1] for probability-like metrics
            return max(0.0, min(1.0, random.gauss(state.mu, sigma)))

    def rank_policies_thompson(
        self,
        policy_states: dict[str, PosteriorState],
    ) -> list[str]:
        """Rank policy IDs by Thompson sampling from their posteriors.

        Args:
            policy_states: {policy_id: PosteriorState} for one metric

        Returns:
            List of policy_ids ranked best-first (highest sample).
        """
        samples = {pid: self.thompson_sample(state) for pid, state in policy_states.items()}
        return sorted(samples, key=lambda pid: samples[pid], reverse=True)

    def rank_policies_ucb(
        self,
        policy_states: dict[str, PosteriorState],
        c: float = 2.0,
    ) -> list[str]:
        """Rank policy IDs by UCB score.

        UCB = mean + c * sqrt(variance / max(n, 1))
        """
        scores: dict[str, float] = {}
        for pid, state in policy_states.items():
            summary = self.get_posterior_summary(state)
            ucb = summary.mean + c * math.sqrt(summary.variance / max(summary.sample_size, 1))
            scores[pid] = ucb
        return sorted(scores, key=lambda pid: scores[pid], reverse=True)

    # ---------------------
    # Persistence
    # ---------------------

    def persist_posterior(self, repo, state: PosteriorState) -> None:
        """Upsert a posterior state in bt_bayesian_posteriors."""
        history_json = json.dumps(state.update_history[-MAX_HISTORY_ENTRIES:])
        repo.db.execute(
            """INSERT INTO bt_bayesian_posteriors
               (policy_id, domain, metric_name, observation_unit, distribution_type,
                alpha, beta, mu, M2, n, last_updated, update_history_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(policy_id, domain, metric_name) DO UPDATE SET
                 alpha=excluded.alpha, beta=excluded.beta,
                 mu=excluded.mu, M2=excluded.M2, n=excluded.n,
                 last_updated=excluded.last_updated,
                 update_history_json=excluded.update_history_json""",
            (
                state.policy_id, state.domain, state.metric_name,
                state.observation_unit, state.distribution_type,
                state.alpha, state.beta, state.mu, state.M2, state.n,
                state.last_updated or _utcnow(),
                history_json,
            ),
        )
        repo.db.commit()

    def load_posteriors(
        self, repo, policy_id: str, domain: str
    ) -> dict[str, PosteriorState]:
        """Load all posteriors for a given policy/domain pair."""
        rows = repo.db.execute(
            "SELECT * FROM bt_bayesian_posteriors WHERE policy_id=? AND domain=?",
            (policy_id, domain),
        ).fetchall()
        result = {}
        for r in rows:
            d = dict(r)
            history = json.loads(d.get("update_history_json") or "[]")
            state = PosteriorState(
                policy_id=d["policy_id"],
                domain=d["domain"],
                metric_name=d["metric_name"],
                observation_unit=d["observation_unit"],
                distribution_type=d["distribution_type"],
                alpha=d["alpha"],
                beta=d["beta"],
                mu=d["mu"],
                M2=d["M2"],
                n=d["n"],
                last_updated=d["last_updated"],
                update_history=history,
            )
            result[d["metric_name"]] = state
        return result

    def get_or_create_posterior(
        self, repo, policy_id: str, domain: str, metric_name: str
    ) -> PosteriorState:
        """Load posterior if it exists, otherwise create a new uninformative prior."""
        states = self.load_posteriors(repo, policy_id, domain)
        if metric_name in states:
            return states[metric_name]
        return self.new_state(policy_id, domain, metric_name)

    # ---------------------
    # Explainability
    # ---------------------

    def explain_update(
        self,
        old_state: PosteriorState,
        new_state: PosteriorState,
        outcome: float,
    ) -> str:
        """Describe what changed in a posterior update."""
        old_summary = self.get_posterior_summary(old_state)
        new_summary = self.get_posterior_summary(new_state)
        delta = new_summary.mean - old_summary.mean
        direction = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        return (
            f"Prior: mean={old_summary.mean:.3f} "
            f"({old_summary.uncertainty_label} uncertainty, n={old_summary.sample_size})\n"
            f"Observation: {outcome:.3f}\n"
            f"Posterior: mean={new_summary.mean:.3f} "
            f"({new_summary.uncertainty_label} uncertainty, n={new_summary.sample_size})\n"
            f"Change: {direction}{abs(delta):.3f} in mean"
        )

    # ---------------------
    # Phase 8: Review-label posterior updates
    # ---------------------

    def new_reviewed_state(
        self,
        policy_id: str,
        domain: str,
        metric_name: str,
    ) -> PosteriorState:
        """Create a weakly informative prior state for a reviewed metric.

        Review metrics use Beta(2,2) for binary (50% prior with 4 pseudo-obs)
        to prevent sparse labels from dominating too aggressively.
        """
        if metric_name in REVIEWED_BINARY_METRICS:
            prior = REVIEWED_BINARY_PRIOR
            return PosteriorState(
                policy_id=policy_id,
                domain=domain,
                metric_name=metric_name,
                observation_unit=REVIEWED_BINARY_METRICS[metric_name],
                distribution_type="beta_binomial",
                alpha=prior["alpha"],
                beta=prior["beta"],
            )
        elif metric_name in REVIEWED_CONTINUOUS_METRICS:
            prior = REVIEWED_CONTINUOUS_PRIOR
            return PosteriorState(
                policy_id=policy_id,
                domain=domain,
                metric_name=metric_name,
                observation_unit=REVIEWED_CONTINUOUS_METRICS[metric_name],
                distribution_type="normal_approx",
                mu=prior["mu"],
                M2=prior["M2"],
                n=prior["n"],
            )
        else:
            raise ValueError(f"Unknown reviewed metric: {metric_name}")

    def update_from_review_label(
        self,
        states: dict[str, PosteriorState],
        policy_id: str,
        domain: str,
        label: dict,
    ) -> dict[str, PosteriorState]:
        """Update reviewed posteriors from a single review label dict.

        Args:
            states: Current {metric_name: PosteriorState} for this policy/domain
            policy_id: Policy this label is attributed to
            domain: Domain (e.g. "clean-energy")
            label: Review label dict with keys:
                - decision: "approve" | "reject" | "defer"
                - novelty_confidence: float 0-1
                - technical_plausibility: float 0-1
                - commercialization_relevance: float 0-1

        Returns:
            Updated {metric_name: PosteriorState}
        """
        updated = dict(states)

        # Update review_label_approval (binary)
        decision = label.get("decision", "defer")
        if decision in ("approve", "reject"):
            metric = "review_label_approval"
            state = updated.get(metric) or self.new_reviewed_state(policy_id, domain, metric)
            success = decision == "approve"
            updated[metric] = self.update_binary(state, success)

        # Update continuous reviewed metrics (always, regardless of decision)
        for metric, key in [
            ("review_novelty_confidence", "novelty_confidence"),
            ("review_technical_plausibility", "technical_plausibility"),
            ("review_commercialization_relevance", "commercialization_relevance"),
        ]:
            if key in label and label[key] is not None:
                state = updated.get(metric) or self.new_reviewed_state(policy_id, domain, metric)
                try:
                    value = float(label[key])
                    updated[metric] = self.update_continuous(state, value)
                except (TypeError, ValueError):
                    pass

        return updated

    def get_reviewed_posterior_means(
        self, states: dict[str, PosteriorState]
    ) -> dict[str, Optional[float]]:
        """Return mean estimates for all reviewed metrics.

        Returns None for metrics with no real observations (only prior).
        """
        result: dict[str, Optional[float]] = {}
        for metric in list(REVIEWED_BINARY_METRICS) + list(REVIEWED_CONTINUOUS_METRICS):
            state = states.get(metric)
            if state is None:
                result[metric] = None
                continue
            summary = self.get_posterior_summary(state)
            # Report None if only prior pseudo-observations exist
            if summary.sample_size == 0:
                result[metric] = None
            else:
                result[metric] = summary.mean
        return result

    def summarize_reviewed_posteriors(
        self,
        states: dict[str, PosteriorState],
    ) -> dict:
        """Return a full summary dict of all reviewed posteriors."""
        summary = {}
        all_metrics = list(REVIEWED_BINARY_METRICS) + list(REVIEWED_CONTINUOUS_METRICS)
        for metric in all_metrics:
            state = states.get(metric)
            if state is None:
                summary[metric] = {
                    "mean": None,
                    "sample_size": 0,
                    "uncertainty_label": "high",
                    "note": "no observations",
                }
            else:
                ps = self.get_posterior_summary(state)
                summary[metric] = ps.to_dict()
        return summary

    def get_or_create_reviewed_posterior(
        self, repo, policy_id: str, domain: str, metric_name: str
    ) -> PosteriorState:
        """Load reviewed posterior if exists, otherwise create new weakly informative prior."""
        states = self.load_posteriors(repo, policy_id, domain)
        if metric_name in states:
            return states[metric_name]
        if metric_name in REVIEWED_BINARY_METRICS or metric_name in REVIEWED_CONTINUOUS_METRICS:
            return self.new_reviewed_state(policy_id, domain, metric_name)
        return self.new_state(policy_id, domain, metric_name)

    # ---------------------
    # Helpers
    # ---------------------

    @staticmethod
    def _beta_mean(alpha: float, beta: float) -> float:
        return alpha / (alpha + beta)

    @staticmethod
    def _beta_variance(alpha: float, beta: float) -> float:
        s = alpha + beta
        return (alpha * beta) / (s * s * (s + 1))
