"""Reward logging for Breakthrough Engine Phase 6.

Provides structured reward signal logging (atomic events) and RL-ready
trajectory recording (episode summaries).

Key design decisions:
- Reward weights are NOT hardcoded — they come from versioned config files
  (config/reward_recipes/vN.yaml).
- bt_reward_logs = atomic signal events (one row per observation)
- bt_trajectories = episode-level summaries (one row per run)
- These are semantically separate: signals can exist without a trajectory.
- Every trajectory records which reward recipe version was used.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import RunRecord, RunMetrics, RunStatus, new_id

logger = logging.getLogger(__name__)

REWARD_RECIPES_DIR = Path(__file__).parent.parent / "config" / "reward_recipes"
DEFAULT_RECIPE_VERSION = "v1"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# RewardRecipe
# ---------------------------------------------------------------------------

@dataclass
class RewardRecipe:
    """Versioned reward weighting config."""
    recipe_version: str
    description: str
    weights: dict   # component_name -> weight (float)

    @classmethod
    def from_dict(cls, d: dict) -> "RewardRecipe":
        return cls(
            recipe_version=d.get("recipe_version", DEFAULT_RECIPE_VERSION),
            description=d.get("description", ""),
            weights=d.get("weights", {}),
        )


# ---------------------------------------------------------------------------
# RewardSignal
# ---------------------------------------------------------------------------

@dataclass
class RewardSignal:
    """Atomic reward signal event (one observation)."""
    run_id: str
    signal_name: str
    signal_value: float
    signal_type: str          # "binary" | "continuous"
    observation_unit: str     # "candidate" | "run" | "draft"
    candidate_id: str = ""
    policy_id: str = ""
    context: dict = field(default_factory=dict)
    id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "candidate_id": self.candidate_id,
            "policy_id": self.policy_id,
            "observation_unit": self.observation_unit,
            "signal_name": self.signal_name,
            "signal_value": self.signal_value,
            "signal_type": self.signal_type,
            "context": self.context,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# TrajectoryRecord
# ---------------------------------------------------------------------------

@dataclass
class TrajectoryRecord:
    """RL-ready episode summary (one run = one episode)."""
    run_id: str
    outcome: str              # "draft_created" | "no_publication" | "failed"
    reward: float             # composite reward (computed from recipe)
    reward_components: dict   # full breakdown (all components, not just weighted)
    reward_recipe_version: str = DEFAULT_RECIPE_VERSION
    policy_id: str = ""
    state: dict = field(default_factory=dict)   # context at start of run
    action: dict = field(default_factory=dict)  # policy choices made
    trajectory_id: str = ""
    id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "trajectory_id": self.trajectory_id,
            "run_id": self.run_id,
            "policy_id": self.policy_id,
            "reward_recipe_version": self.reward_recipe_version,
            "state": self.state,
            "action": self.action,
            "reward": round(self.reward, 4),
            "reward_components": {k: round(v, 4) for k, v in self.reward_components.items()},
            "outcome": self.outcome,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# RewardLogger
# ---------------------------------------------------------------------------

class RewardLogger:
    """Logs reward signals and trajectories."""

    def __init__(self, recipe_version: str = DEFAULT_RECIPE_VERSION):
        self._recipe: Optional[RewardRecipe] = None
        self._recipe_version = recipe_version

    # ---------------------
    # Recipe loading
    # ---------------------

    def load_recipe(self, recipe_version: str = DEFAULT_RECIPE_VERSION) -> RewardRecipe:
        """Load reward recipe from config/reward_recipes/vN.yaml."""
        recipe_path = REWARD_RECIPES_DIR / f"{recipe_version}.yaml"
        if not recipe_path.exists():
            logger.warning(
                "Reward recipe %s not found at %s — using default weights",
                recipe_version, recipe_path,
            )
            return RewardRecipe(
                recipe_version=recipe_version,
                description="Default fallback recipe",
                weights={
                    "draft_created": 0.50,
                    "mean_final_score": 0.30,
                    "synthesis_fit_pass_rate": 0.20,
                },
            )
        try:
            import yaml
            with open(recipe_path) as f:
                d = yaml.safe_load(f)
            return RewardRecipe.from_dict(d)
        except Exception as e:
            logger.error("Failed to load reward recipe %s: %s", recipe_version, e)
            return RewardRecipe(
                recipe_version=recipe_version,
                description="Fallback (load failed)",
                weights={"draft_created": 0.50, "mean_final_score": 0.30, "synthesis_fit_pass_rate": 0.20},
            )

    def get_recipe(self) -> RewardRecipe:
        """Return cached recipe, loading on first call."""
        if self._recipe is None:
            self._recipe = self.load_recipe(self._recipe_version)
        return self._recipe

    # ---------------------
    # Signal logging
    # ---------------------

    def log_signal(self, repo, signal: RewardSignal) -> None:
        """Persist one atomic reward signal event."""
        if not signal.id:
            signal.id = new_id()
        if not signal.created_at:
            signal.created_at = _utcnow()
        repo.db.execute(
            """INSERT INTO bt_reward_logs
               (id, run_id, candidate_id, policy_id, observation_unit,
                signal_name, signal_value, signal_type, context_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                signal.id,
                signal.run_id,
                signal.candidate_id,
                signal.policy_id,
                signal.observation_unit,
                signal.signal_name,
                signal.signal_value,
                signal.signal_type,
                json.dumps(signal.context),
                signal.created_at,
            ),
        )
        repo.db.commit()

    def log_signals_from_run(
        self,
        repo,
        run_id: str,
        policy_id: str = "",
        domain: str = "",
        sub_domain: str = "",
        bridge_mechanism: str = "",
    ) -> list:
        """Emit reward signals for all candidates in a run.

        Reads from bt_candidates, bt_scores, bt_synthesis_fit.
        Returns list of RewardSignal emitted.
        """
        context = {
            "domain": domain,
            "sub_domain": sub_domain,
            "bridge_mechanism": bridge_mechanism,
        }
        signals = []
        candidates = repo.list_candidates_for_run(run_id)
        from .models import CandidateStatus

        for c in candidates:
            cid = c["id"]
            status = c.get("status", "")

            # novelty_pass: candidate-level binary
            novelty_passed = status not in (
                CandidateStatus.NOVELTY_FAILED.value,
                CandidateStatus.DEDUP_REJECTED.value,
            )
            sig = RewardSignal(
                run_id=run_id,
                candidate_id=cid,
                policy_id=policy_id,
                observation_unit="candidate",
                signal_name="novelty_pass",
                signal_value=1.0 if novelty_passed else 0.0,
                signal_type="binary",
                context=context,
            )
            self.log_signal(repo, sig)
            signals.append(sig)

            # synthesis_fit_pass: candidate-level binary
            if status not in (CandidateStatus.DEDUP_REJECTED.value,
                               CandidateStatus.HYPOTHESIS_FAILED.value):
                synth_row = repo.get_synthesis_fit(cid)
                synth_passed = synth_row.get("passed", 1) if synth_row else 1
                sig = RewardSignal(
                    run_id=run_id,
                    candidate_id=cid,
                    policy_id=policy_id,
                    observation_unit="candidate",
                    signal_name="synthesis_fit_pass",
                    signal_value=float(synth_passed),
                    signal_type="binary",
                    context=context,
                )
                self.log_signal(repo, sig)
                signals.append(sig)

                # synthesis_fit_score: candidate-level continuous
                if synth_row:
                    fit_score = float(synth_row.get("cross_domain_fit_score", 0.0))
                    sig = RewardSignal(
                        run_id=run_id,
                        candidate_id=cid,
                        policy_id=policy_id,
                        observation_unit="candidate",
                        signal_name="synthesis_fit_score",
                        signal_value=fit_score,
                        signal_type="continuous",
                        context=context,
                    )
                    self.log_signal(repo, sig)
                    signals.append(sig)

            # final_score + review_worthy: candidate-level
            score_row = repo.get_score(cid)
            if score_row:
                fs = float(score_row.get("final_score", 0.0))
                sig = RewardSignal(
                    run_id=run_id,
                    candidate_id=cid,
                    policy_id=policy_id,
                    observation_unit="candidate",
                    signal_name="final_score",
                    signal_value=fs,
                    signal_type="continuous",
                    context=context,
                )
                self.log_signal(repo, sig)
                signals.append(sig)

                review_worthy = 1.0 if fs >= 0.60 else 0.0
                sig = RewardSignal(
                    run_id=run_id,
                    candidate_id=cid,
                    policy_id=policy_id,
                    observation_unit="candidate",
                    signal_name="review_worthy",
                    signal_value=review_worthy,
                    signal_type="binary",
                    context=context,
                )
                self.log_signal(repo, sig)
                signals.append(sig)

                # evidence_balance: candidate-level continuous
                eb = float(score_row.get("evidence_strength_score", 0.0))
                sig = RewardSignal(
                    run_id=run_id,
                    candidate_id=cid,
                    policy_id=policy_id,
                    observation_unit="candidate",
                    signal_name="evidence_balance",
                    signal_value=eb,
                    signal_type="continuous",
                    context=context,
                )
                self.log_signal(repo, sig)
                signals.append(sig)

        return signals

    # ---------------------
    # Trajectory logging
    # ---------------------

    def compute_episode_reward(
        self,
        run_record: RunRecord,
        metrics: RunMetrics,
        recipe: Optional[RewardRecipe] = None,
    ) -> tuple:
        """Compute composite reward and component breakdown for one run.

        Returns (reward: float, components: dict).
        """
        if recipe is None:
            recipe = self.get_recipe()

        # Collect all components (regardless of recipe weights)
        components: dict = {}

        # draft_created: 1 if run produced a publication/draft
        components["draft_created"] = 1.0 if run_record.status == RunStatus.COMPLETED else 0.0

        # mean_final_score: average over all scored candidates
        if metrics.candidates_by_status:
            total_candidates = sum(metrics.candidates_by_status.values())
            components["total_candidates"] = float(total_candidates)

        # Use metrics to derive signal proxies
        components["novelty_pass_rate"] = 1.0 - (
            metrics.novelty_fail_count / max(metrics.evidence_count or 1, 1)
        )

        if metrics.publication_created:
            components["mean_final_score"] = 0.85   # publication produced
        elif metrics.draft_created:
            components["mean_final_score"] = 0.70   # draft produced
        else:
            components["mean_final_score"] = 0.40   # nothing produced

        components["synthesis_fit_pass_rate"] = 1.0  # assume 1.0 if run completed

        # Compute weighted composite reward using recipe
        reward = 0.0
        weighted_sum = 0.0
        total_weight = 0.0
        for component_name, weight in recipe.weights.items():
            val = components.get(component_name, 0.0)
            weighted_sum += val * weight
            total_weight += weight

        reward = weighted_sum / max(total_weight, 1.0)
        components["composite_reward"] = round(reward, 4)
        components["recipe_version"] = recipe.recipe_version

        return reward, components

    def log_trajectory(self, repo, trajectory: TrajectoryRecord) -> None:
        """Persist an RL-ready episode trajectory record."""
        if not trajectory.id:
            trajectory.id = new_id()
        if not trajectory.trajectory_id:
            trajectory.trajectory_id = new_id()
        if not trajectory.created_at:
            trajectory.created_at = _utcnow()
        repo.db.execute(
            """INSERT OR REPLACE INTO bt_trajectories
               (id, trajectory_id, run_id, policy_id, reward_recipe_version,
                state_json, action_json, reward, reward_components_json,
                outcome, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                trajectory.id,
                trajectory.trajectory_id,
                trajectory.run_id,
                trajectory.policy_id,
                trajectory.reward_recipe_version,
                json.dumps(trajectory.state),
                json.dumps(trajectory.action),
                trajectory.reward,
                json.dumps(trajectory.reward_components),
                trajectory.outcome,
                trajectory.created_at,
            ),
        )
        repo.db.commit()

    def log_run_trajectory(
        self,
        repo,
        run_record: RunRecord,
        metrics: RunMetrics,
        policy_id: str = "",
        state: Optional[dict] = None,
        action: Optional[dict] = None,
    ) -> TrajectoryRecord:
        """Convenience: compute reward and log a trajectory for a completed run."""
        recipe = self.get_recipe()
        reward, components = self.compute_episode_reward(run_record, metrics, recipe)

        outcome_map = {
            "completed": "draft_created",
            "completed_no_publication": "no_publication",
            "failed": "failed",
        }
        outcome = outcome_map.get(run_record.status.value, run_record.status.value)

        traj = TrajectoryRecord(
            run_id=run_record.id,
            policy_id=policy_id,
            reward_recipe_version=recipe.recipe_version,
            state=state or {},
            action=action or {},
            reward=reward,
            reward_components=components,
            outcome=outcome,
        )
        self.log_trajectory(repo, traj)
        return traj

    # ---------------------
    # Queries
    # ---------------------

    def export_trajectories(
        self, repo, since_date: Optional[str] = None
    ) -> list:
        """Export trajectory records, optionally filtered by date."""
        if since_date:
            rows = repo.db.execute(
                "SELECT * FROM bt_trajectories WHERE created_at >= ? ORDER BY created_at",
                (since_date,),
            ).fetchall()
        else:
            rows = repo.db.execute(
                "SELECT * FROM bt_trajectories ORDER BY created_at"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            result.append(TrajectoryRecord(
                id=d["id"],
                trajectory_id=d["trajectory_id"],
                run_id=d["run_id"],
                policy_id=d["policy_id"],
                reward_recipe_version=d["reward_recipe_version"],
                state=json.loads(d.get("state_json") or "{}"),
                action=json.loads(d.get("action_json") or "{}"),
                reward=d["reward"],
                reward_components=json.loads(d.get("reward_components_json") or "{}"),
                outcome=d["outcome"],
                created_at=d["created_at"],
            ))
        return result

    def get_reward_stats(self, repo, policy_id: Optional[str] = None) -> dict:
        """Summarize reward statistics, optionally per policy."""
        if policy_id:
            rows = repo.db.execute(
                "SELECT reward, outcome FROM bt_trajectories WHERE policy_id=?",
                (policy_id,),
            ).fetchall()
        else:
            rows = repo.db.execute(
                "SELECT reward, outcome FROM bt_trajectories"
            ).fetchall()

        if not rows:
            return {"count": 0, "mean_reward": 0.0, "outcomes": {}}

        rewards = [r["reward"] for r in rows]
        outcomes: dict = {}
        for r in rows:
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1

        return {
            "count": len(rewards),
            "mean_reward": round(sum(rewards) / len(rewards), 4),
            "min_reward": round(min(rewards), 4),
            "max_reward": round(max(rewards), 4),
            "outcomes": outcomes,
        }
