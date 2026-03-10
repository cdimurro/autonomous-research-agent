"""Policy registry for the Breakthrough Engine Phase 6.

A policy is a named set of configurable runtime choices (prompt variant,
diversity steering, rotation policy, etc.) that can be evaluated against
the champion and promoted or rolled back based on Bayesian evidence.

Champion/Challenger model:
- One policy is always the champion (default: Phase 5 validated settings)
- Challengers are registered and trialed
- Promotion is two-stage: Challenger → Probation → Full Champion
- Rollback is always available and logs the reason
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .models import new_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default champion (Phase 5 validated settings)
# ---------------------------------------------------------------------------

PHASE5_CHAMPION_ID = "phase5_champion"
PHASE5_CHAMPION_VERSION = "5.0"

# Promotion thresholds (conjunctive — all must be met)
PROMOTION_THRESHOLDS = {
    "novelty_pass_rate": -0.05,        # challenger >= champion - 0.05
    "top_candidate_final_score": -0.03,
    "falsification_pass_rate": -0.05,
    "operator_burden_proxy": +0.05,    # challenger <= champion + 0.05 (lower burden)
    "draft_quality_proxy": -0.03,
}
PROMOTION_MIN_TRIALS = 5
FULL_CHAMPION_MIN_PROBATION_RUNS = 3
REGRESSION_THRESHOLD = 0.05

# Phase 8: Review-signal promotion thresholds (applied when labels are available)
REVIEWED_PROMOTION_THRESHOLDS = {
    "review_approval_rate": -0.05,       # challenger >= champion - 0.05
    "review_novelty_confidence": -0.05,
    "review_technical_plausibility": -0.05,
    "review_reject_rate": +0.05,         # challenger <= champion + 0.05 (lower rejection is better)
}
# Max active challengers at any time
MAX_ACTIVE_CHALLENGERS = 2

# Policy states
POLICY_STATE_CHALLENGER = "challenger"
POLICY_STATE_PROBATIONARY_CHAMPION = "probationary_champion"
POLICY_STATE_CHAMPION = "champion"
POLICY_STATE_ROLLED_BACK = "rolled_back"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PolicyConfig:
    """A named set of configurable runtime choices."""
    name: str
    version: str = "1.0"
    description: str = ""
    # Configurable runtime choices
    generation_prompt_variant: str = "standard"     # standard|synthesis_focus|evidence_heavy
    diversity_steering_variant: str = "standard"    # standard|aggressive|conservative
    sub_domain_rotation_policy: str = "auto"        # auto|fixed|random
    bridge_selection_policy: str = "auto"           # auto|fixed|random
    evidence_ranking_weights: Optional[dict] = None  # None = program defaults
    negative_memory_strategy: str = "standard"      # standard|strict|permissive
    review_gating_heuristics: list = field(default_factory=list)
    scoring_weights: Optional[dict] = None           # None = program defaults
    metadata: dict = field(default_factory=dict)
    # Assigned by registry
    id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "generation_prompt_variant": self.generation_prompt_variant,
            "diversity_steering_variant": self.diversity_steering_variant,
            "sub_domain_rotation_policy": self.sub_domain_rotation_policy,
            "bridge_selection_policy": self.bridge_selection_policy,
            "evidence_ranking_weights": self.evidence_ranking_weights,
            "negative_memory_strategy": self.negative_memory_strategy,
            "review_gating_heuristics": self.review_gating_heuristics,
            "scoring_weights": self.scoring_weights,
            "metadata": self.metadata,
            "id": self.id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PolicyConfig":
        return cls(
            name=d.get("name", ""),
            version=d.get("version", "1.0"),
            description=d.get("description", ""),
            generation_prompt_variant=d.get("generation_prompt_variant", "standard"),
            diversity_steering_variant=d.get("diversity_steering_variant", "standard"),
            sub_domain_rotation_policy=d.get("sub_domain_rotation_policy", "auto"),
            bridge_selection_policy=d.get("bridge_selection_policy", "auto"),
            evidence_ranking_weights=d.get("evidence_ranking_weights"),
            negative_memory_strategy=d.get("negative_memory_strategy", "standard"),
            review_gating_heuristics=d.get("review_gating_heuristics", []),
            scoring_weights=d.get("scoring_weights"),
            metadata=d.get("metadata", {}),
            id=d.get("id", ""),
            created_at=d.get("created_at", ""),
        )


@dataclass
class PolicyTrial:
    """Record of one policy evaluation episode."""
    id: str = ""
    policy_id: str = ""
    trial_type: str = "benchmark"       # benchmark|production|challenger_eval
    benchmark_metrics: dict = field(default_factory=dict)
    posterior_summary: dict = field(default_factory=dict)
    outcome: str = ""                   # champion_improved|champion_maintained|challenger_failed
    started_at: str = ""
    completed_at: str = ""


# ---------------------------------------------------------------------------
# Default Phase 5 champion
# ---------------------------------------------------------------------------

def _default_champion() -> PolicyConfig:
    return PolicyConfig(
        id=PHASE5_CHAMPION_ID,
        name="phase5_champion",
        version=PHASE5_CHAMPION_VERSION,
        description="Validated Phase 5 settings. Standard diversity, auto rotation, standard synthesis.",
        generation_prompt_variant="standard",
        diversity_steering_variant="standard",
        sub_domain_rotation_policy="auto",
        bridge_selection_policy="auto",
        evidence_ranking_weights=None,
        negative_memory_strategy="standard",
        scoring_weights=None,
        metadata={"phase": 5, "validated_tag": "breakthrough-engine-phase5-validated"},
        created_at=_utcnow(),
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class PolicyRegistry:
    """Manages champion/challenger policies with two-stage promotion."""

    def __init__(self, repo):
        self.repo = repo
        self._ensure_default_champion()

    def _ensure_default_champion(self) -> None:
        """Seed the champion if no policies exist."""
        existing = self._db_get_champion()
        if existing is None:
            champion = _default_champion()
            self._db_save_policy(champion, is_champion=1, is_probation=0)
            logger.info("PolicyRegistry: seeded default Phase 5 champion")

    # -- Public API --

    def register(self, config: PolicyConfig) -> PolicyConfig:
        """Register a challenger policy."""
        if not config.id:
            config.id = new_id()
        config.created_at = _utcnow()
        self._db_save_policy(config, is_champion=0, is_probation=0)
        logger.info("PolicyRegistry: registered challenger '%s' (id=%s)", config.name, config.id)
        return config

    def get_champion(self) -> PolicyConfig:
        """Return the current champion policy."""
        row = self._db_get_champion()
        if row is None:
            self._ensure_default_champion()
            row = self._db_get_champion()
        return PolicyConfig.from_dict(json.loads(row["config_json"]))

    def get_challengers(self) -> list[PolicyConfig]:
        """Return all non-champion, non-probation policies."""
        rows = self.repo.db.execute(
            "SELECT * FROM bt_policies WHERE is_champion=0 AND is_probation=0 ORDER BY created_at DESC"
        ).fetchall()
        return [PolicyConfig.from_dict(json.loads(r["config_json"])) for r in rows]

    def get_probation_policies(self) -> list[PolicyConfig]:
        """Return policies in probation stage."""
        rows = self.repo.db.execute(
            "SELECT * FROM bt_policies WHERE is_probation=1 ORDER BY created_at DESC"
        ).fetchall()
        return [PolicyConfig.from_dict(json.loads(r["config_json"])) for r in rows]

    def get_policy(self, policy_id: str) -> Optional[PolicyConfig]:
        """Get any policy by ID."""
        row = self.repo.db.execute(
            "SELECT * FROM bt_policies WHERE id=?", (policy_id,)
        ).fetchone()
        if row is None:
            return None
        return PolicyConfig.from_dict(json.loads(dict(row)["config_json"]))

    def promote_to_probation(
        self,
        policy_id: str,
        evidence: dict,
    ) -> tuple[bool, str]:
        """Try to promote a challenger to probation status.

        Returns (success, reason).
        The evidence dict should contain:
            - 'posterior_means': dict of metric_name -> challenger mean
            - 'champion_means': dict of metric_name -> champion mean
            - 'trial_count': int
        """
        challenger = self.get_policy(policy_id)
        if challenger is None:
            return False, f"Policy {policy_id} not found"

        champion = self.get_champion()
        posterior_means = evidence.get("posterior_means", {})
        champion_means = evidence.get("champion_means", {})
        trial_count = evidence.get("trial_count", 0)

        if trial_count < PROMOTION_MIN_TRIALS:
            return False, f"Insufficient trials: {trial_count} < {PROMOTION_MIN_TRIALS} required"

        failures = []
        for metric, delta_threshold in PROMOTION_THRESHOLDS.items():
            challenger_val = posterior_means.get(metric)
            champion_val = champion_means.get(metric)
            if challenger_val is None or champion_val is None:
                logger.debug("Skipping promotion check for %s (no data)", metric)
                continue
            if metric == "operator_burden_proxy":
                # Lower is better — challenger must be <= champion + threshold
                if challenger_val > champion_val + abs(delta_threshold):
                    failures.append(
                        f"{metric}: challenger={challenger_val:.3f} > champion+threshold={champion_val + abs(delta_threshold):.3f}"
                    )
            else:
                # Higher is better — challenger must be >= champion + delta (negative delta = tolerance)
                if challenger_val < champion_val + delta_threshold:
                    failures.append(
                        f"{metric}: challenger={challenger_val:.3f} < champion+threshold={champion_val + delta_threshold:.3f}"
                    )

        if failures:
            reason = "Promotion criteria not met: " + "; ".join(failures)
            logger.info("PolicyRegistry: promotion denied for '%s': %s", policy_id, reason)
            return False, reason

        # Promote to probation
        self.repo.db.execute(
            "UPDATE bt_policies SET is_probation=1 WHERE id=?", (policy_id,)
        )
        self.repo.db.commit()
        logger.info("PolicyRegistry: promoted '%s' to probation", policy_id)
        return True, "Promoted to probation"

    def promote_to_champion(
        self,
        policy_id: str,
        reason: str = "",
    ) -> tuple[bool, str]:
        """Promote a probation policy to full champion.

        Requires the policy to be in probation status.
        """
        row = self.repo.db.execute(
            "SELECT * FROM bt_policies WHERE id=? AND is_probation=1", (policy_id,)
        ).fetchone()
        if row is None:
            return False, f"Policy {policy_id} not in probation"

        # Get current champion
        champ_row = self._db_get_champion()
        prev_champion_id = champ_row["id"] if champ_row else ""

        # Demote current champion
        if champ_row:
            self.repo.db.execute(
                "UPDATE bt_policies SET is_champion=0 WHERE id=?", (champ_row["id"],)
            )

        # Promote probation policy
        self.repo.db.execute(
            """UPDATE bt_policies
               SET is_champion=1, is_probation=0, previous_champion_id=?
               WHERE id=?""",
            (prev_champion_id, policy_id),
        )
        self.repo.db.commit()
        logger.info(
            "PolicyRegistry: '%s' promoted to champion (previous: %s) reason=%r",
            policy_id, prev_champion_id, reason,
        )
        return True, f"Promoted to champion (previous: {prev_champion_id})"

    def rollback_champion(self, reason: str = "") -> tuple[bool, str]:
        """Roll back to previous champion."""
        champ_row = self._db_get_champion()
        if champ_row is None:
            return False, "No current champion found"

        prev_id = dict(champ_row).get("previous_champion_id", "")
        if not prev_id:
            return False, "No previous champion to roll back to"

        prev_row = self.repo.db.execute(
            "SELECT * FROM bt_policies WHERE id=?", (prev_id,)
        ).fetchone()
        if prev_row is None:
            return False, f"Previous champion {prev_id} not found"

        demoted_id = champ_row["id"]
        demoted_name = dict(champ_row).get("name", demoted_id)

        # Mark demoted champion as rolled_back (best-effort — column may not exist in old DBs)
        try:
            self.repo.db.execute(
                "UPDATE bt_policies SET is_champion=0, is_probation=0, is_rolled_back=1 WHERE id=?",
                (demoted_id,),
            )
        except Exception:
            self.repo.db.execute(
                "UPDATE bt_policies SET is_champion=0, is_probation=0 WHERE id=?",
                (demoted_id,),
            )
        # Restore previous champion
        self.repo.db.execute(
            "UPDATE bt_policies SET is_champion=1, is_probation=0 WHERE id=?",
            (prev_id,),
        )
        self.repo.db.commit()
        logger.info(
            "PolicyRegistry: rolled back to '%s' from '%s', reason=%r",
            prev_id, demoted_id, reason,
        )

        # Log the rollback event
        self._log_promotion_event(
            policy_id=demoted_id,
            policy_name=demoted_name,
            event_type="rollback",
            from_state=POLICY_STATE_CHAMPION,
            to_state=POLICY_STATE_ROLLED_BACK,
            reason=reason,
            evidence={},
        )
        return True, f"Rolled back to {prev_id}"

    # -- Phase 8: Review-signal promotion gate --

    def check_reviewed_promotion_criteria(
        self,
        policy_id: str,
        review_signal: dict,
        champion_review_signal: dict,
    ) -> tuple[bool, str, list[str]]:
        """Check whether a challenger meets review-signal promotion criteria.

        Args:
            policy_id: Challenger policy ID
            review_signal: {metric: value} for the challenger's reviewed posteriors
            champion_review_signal: {metric: value} for the champion's reviewed posteriors

        Returns:
            (passed, summary, failures) — failures is empty if passed
        """
        if not review_signal or not champion_review_signal:
            return True, "review-signal gate skipped (no labels available)", []

        failures = []
        for metric, delta_threshold in REVIEWED_PROMOTION_THRESHOLDS.items():
            challenger_val = review_signal.get(metric)
            champion_val = champion_review_signal.get(metric)
            if challenger_val is None or champion_val is None:
                continue

            if metric == "review_reject_rate":
                # Lower is better — challenger must be <= champion + threshold
                if challenger_val > champion_val + abs(delta_threshold):
                    failures.append(
                        f"{metric}: challenger={challenger_val:.3f} > champion+threshold={champion_val + abs(delta_threshold):.3f}"
                    )
            else:
                # Higher is better
                if challenger_val < champion_val + delta_threshold:
                    failures.append(
                        f"{metric}: challenger={challenger_val:.3f} < champion+threshold={champion_val + delta_threshold:.3f}"
                    )

        if failures:
            return False, "Review-signal gate failed: " + "; ".join(failures), failures
        return True, "Review-signal gate passed", []

    def promote_to_champion_reviewed(
        self,
        policy_id: str,
        evidence: dict,
        review_signal: Optional[dict] = None,
        champion_review_signal: Optional[dict] = None,
        reason: str = "",
    ) -> tuple[bool, str]:
        """Promote a probation policy to full champion with review-signal check.

        This is the Phase 8 promoted-to-champion method that also applies
        the review-signal gate when reviewer labels are available.

        Args:
            policy_id: Policy to promote
            evidence: benchmark + posterior evidence dict
            review_signal: Challenger's reviewed posterior means
            champion_review_signal: Champion's reviewed posterior means
            reason: Human-readable reason for promotion
        """
        # First apply review-signal gate
        if review_signal and champion_review_signal:
            passed, gate_msg, failures = self.check_reviewed_promotion_criteria(
                policy_id, review_signal, champion_review_signal
            )
            if not passed:
                logger.info(
                    "PolicyRegistry: reviewed promotion denied for '%s': %s",
                    policy_id, gate_msg,
                )
                return False, gate_msg

        # Delegate to standard promote_to_champion
        success, msg = self.promote_to_champion(policy_id, reason=reason)
        if success:
            # Log the promotion event with evidence
            row = self.repo.db.execute(
                "SELECT * FROM bt_policies WHERE id=?", (policy_id,)
            ).fetchone()
            self._log_promotion_event(
                policy_id=policy_id,
                policy_name=dict(row).get("name", policy_id) if row else policy_id,
                event_type="promoted_to_champion",
                from_state=POLICY_STATE_PROBATIONARY_CHAMPION,
                to_state=POLICY_STATE_CHAMPION,
                reason=reason or msg,
                evidence=evidence,
            )
        return success, msg

    def get_policy_status(self, policy_id: str) -> str:
        """Return the status string for a policy ID."""
        row = self.repo.db.execute(
            "SELECT * FROM bt_policies WHERE id=?", (policy_id,)
        ).fetchone()
        if row is None:
            return "not_found"
        d = dict(row)
        if d.get("is_champion"):
            return POLICY_STATE_CHAMPION
        if d.get("is_probation"):
            return POLICY_STATE_PROBATIONARY_CHAMPION
        if d.get("is_rolled_back"):
            return POLICY_STATE_ROLLED_BACK
        return POLICY_STATE_CHALLENGER

    def count_active_challengers(self) -> int:
        """Return the count of non-champion, non-probation, non-rolled-back policies."""
        try:
            row = self.repo.db.execute(
                "SELECT COUNT(*) as cnt FROM bt_policies WHERE is_champion=0 AND is_probation=0 AND is_rolled_back=0"
            ).fetchone()
        except Exception:
            row = self.repo.db.execute(
                "SELECT COUNT(*) as cnt FROM bt_policies WHERE is_champion=0 AND is_probation=0"
            ).fetchone()
        return row["cnt"] if row else 0

    def can_register_challenger(self) -> tuple[bool, str]:
        """Check whether a new challenger can be registered (bounded by MAX_ACTIVE_CHALLENGERS)."""
        count = self.count_active_challengers()
        if count >= MAX_ACTIVE_CHALLENGERS:
            return False, f"Max active challengers ({MAX_ACTIVE_CHALLENGERS}) reached; retire one first"
        return True, f"OK ({count}/{MAX_ACTIVE_CHALLENGERS} challengers active)"

    def _log_promotion_event(
        self,
        policy_id: str,
        policy_name: str,
        event_type: str,
        from_state: str,
        to_state: str,
        reason: str,
        evidence: dict,
    ) -> None:
        """Log a promotion/rollback event to bt_policy_promotion_log (best-effort)."""
        try:
            self.repo.log_policy_promotion({
                "policy_id": policy_id,
                "policy_name": policy_name,
                "event_type": event_type,
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "evidence_json": json.dumps(evidence),
            })
        except Exception as e:
            logger.debug("Could not log promotion event: %s", e)

    def record_trial(self, trial: PolicyTrial) -> str:
        """Save a policy trial record."""
        if not trial.id:
            trial.id = new_id()
        if not trial.started_at:
            trial.started_at = _utcnow()
        self.repo.db.execute(
            """INSERT OR REPLACE INTO bt_policy_trials
               (id, policy_id, trial_type, benchmark_metrics_json,
                posterior_summary_json, outcome, started_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                trial.id,
                trial.policy_id,
                trial.trial_type,
                json.dumps(trial.benchmark_metrics),
                json.dumps(trial.posterior_summary),
                trial.outcome,
                trial.started_at,
                trial.completed_at or _utcnow(),
            ),
        )
        self.repo.db.commit()
        return trial.id

    def get_trial_history(self, policy_id: Optional[str] = None) -> list[PolicyTrial]:
        """Get trial history, optionally filtered by policy_id."""
        if policy_id:
            rows = self.repo.db.execute(
                "SELECT * FROM bt_policy_trials WHERE policy_id=? ORDER BY started_at DESC",
                (policy_id,),
            ).fetchall()
        else:
            rows = self.repo.db.execute(
                "SELECT * FROM bt_policy_trials ORDER BY started_at DESC"
            ).fetchall()
        return [
            PolicyTrial(
                id=r["id"],
                policy_id=r["policy_id"],
                trial_type=r["trial_type"],
                benchmark_metrics=json.loads(r["benchmark_metrics_json"] or "{}"),
                posterior_summary=json.loads(r["posterior_summary_json"] or "{}"),
                outcome=r["outcome"],
                started_at=r["started_at"],
                completed_at=r["completed_at"] or "",
            )
            for r in rows
        ]

    def list_all(self) -> list[dict]:
        """List all policies with their status."""
        rows = self.repo.db.execute(
            "SELECT id, name, version, is_champion, is_probation, created_at FROM bt_policies ORDER BY created_at"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d["is_champion"]:
                d["status"] = "champion"
            elif d["is_probation"]:
                d["status"] = "probation"
            else:
                d["status"] = "challenger"
            result.append(d)
        return result

    # -- DB helpers --

    def _db_get_champion(self):
        return self.repo.db.execute(
            "SELECT * FROM bt_policies WHERE is_champion=1 LIMIT 1"
        ).fetchone()

    def _db_save_policy(
        self, config: PolicyConfig, is_champion: int = 0, is_probation: int = 0
    ) -> None:
        self.repo.db.execute(
            """INSERT OR REPLACE INTO bt_policies
               (id, name, version, config_json, is_champion, is_probation, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                config.id,
                config.name,
                config.version,
                json.dumps(config.to_dict()),
                is_champion,
                is_probation,
                config.created_at or _utcnow(),
            ),
        )
        self.repo.db.commit()
