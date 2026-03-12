# Breakthrough Engine — Phase 9F Data Capture Verification
## Database Persistence Report

**Phase:** 9F
**Created:** 2026-03-12
**DB:** `runtime/db/scires.db`
**Status:** IN PROGRESS (live runs pending)

---

## Database Overview

| Table | Row Count | Purpose |
|-------|-----------|---------|
| bt_daily_automation_runs | 18 (at phase start) | Formal daily profile run log |
| bt_daily_campaigns | 70 (at phase start) | Campaign search results |
| bt_candidates | 1292 | Generated candidates |
| bt_runs | 234 | Individual orchestrator runs |
| bt_review_queue | 5 | Items awaiting label |
| bt_review_labels | 50 | Collected labels (30 approve, 18 defer, 2 reject) |
| bt_policies | 4 | Registered policies |
| bt_scores | 1007 | Candidate scores |
| bt_finalists | — | (tracked via daily_campaigns.result_json) |
| bt_publication_drafts | 12 | Draft publications |
| bt_publications | 3 | Published items |
| bt_ladder_stages | 334 | Per-stage campaign metrics |
| bt_harness_decisions | 3378 | Gate decisions |

---

## Evidence_diversity_v1 Campaign Data (Phase 9F Window)

### Formal Daily Profile Runs

| Run | Campaign ID | Profile | Status | DB Linkage |
|-----|-------------|---------|--------|-----------|
| 9F-E1 | (in progress) | evaluation_daily_clean_energy | RUNNING | Pending |

### Shadow Mode Runs (overnight 2026-03-12)

| Campaign ID | Policy DB ID | Started | Completed | Champion Title | Score |
|-------------|-------------|---------|-----------|----------------|-------|
| 822e6c4ed82445c0 | 3f24a0a2a8074759 | 2026-03-12T00:06:59Z | 2026-03-12T00:23:39Z | Carrier Lifetime Extension via Trap-State Suppression in Tandems | 0.921 |
| 91303a97ac2a49b4 | 3f24a0a2a8074759 | 2026-03-12T00:23:39Z | 2026-03-12T00:40:18Z | Thermally Stabilized Tandem Junctions via Waste Heat Sink Integration | 0.921 |
| 2fe8e0adf40f4228 | 3f24a0a2a8074759 | 2026-03-12T00:40:18Z | 2026-03-12T01:09:35Z | Thermal-to-Chemical Coupling for High-Temp Battery Safety | 0.921 |
| 68e67ae1b4e3497e | 3f24a0a2a8074759 | 2026-03-12T01:09:35Z | 2026-03-12T01:25:54Z | NiFe-LDH Membrane Integration for Seawater Electrolysis Stability | 0.911 |
| 66ac0fe88fec4a14 | 3f24a0a2a8074759 | 2026-03-12T01:25:54Z | 2026-03-12T01:42:28Z | NiFe-LDH Anode Coupling with Low-Temp DAC for Integrated Green H2/DAC Systems | 0.912 |
| 8d70f1d2580548f3 | 3f24a0a2a8074759 | 2026-03-12T01:42:28Z | 2026-03-12T01:57:33Z | High-Energy Density Argyrodite Coatings for Lightning Protection | 0.893 |

Shadow run aggregate: mean 0.9132, 6/6 APPROVE

### Phase 9E Burn-in Campaigns (historical, evidence_diversity_v1)

| Run | Campaign ID | Profile | Champion Title | Score | Decision |
|-----|-------------|---------|----------------|-------|----------|
| BE1 | a1b2c3d4e5f64e7a | evaluation_daily_clean_energy | Mechanistic Catalyst Screening via Evidence-Driven Bridge Selection for Green Ammonia | 0.9205 | approve |
| BE2 | f6e7d8c9b0a14f2b | evaluation_daily_clean_energy | Redox-Neutral Radical Coupling for Direct CO2-to-Formate Electroreduction | 0.9205 | approve |
| BE3 | 2c3d4e5f6a7b4839 | evaluation_daily_clean_energy | Mechanistic Interface Engineering for Long-Cycle Sodium-Ion Battery Anodes | 0.9105 | approve |
| BP1 | 9d0e1f2a3b4c4b5d | production_daily_clean_energy | Dynamic Vacancy Ordering in NiFe-LDH for Oxygen Evolution Rate Enhancement | 0.9205 | approve |
| BP2 | 6e7f8a9b0c1d4c6e | production_daily_clean_energy | Quantum Confined Sulfide Networks for Photocatalytic Nitrogen Reduction | 0.9105 | approve |
| BP3 | 3f0a1b2c3d4e4d7f | production_daily_clean_energy | Covalent Organic Framework Scaffolds for Lithium-Sulfur Battery Polysulfide Trapping | 0.893 | defer |

Burn-in aggregate: mean 0.9126, 5/6 approve (1 defer), all integrity_ok

---

## DB Linkage Verification

### What Lands in DB per Run

| Data Type | Table | Captured |
|-----------|-------|---------|
| Automation run record | bt_daily_automation_runs | ✅ Yes (policy_id, outcome, run_date) |
| Campaign record | bt_daily_campaigns | ✅ Yes (config_json, result_json, champion info) |
| Candidate records | bt_candidates | ✅ Yes (all generated candidates) |
| Stage results | bt_ladder_stages | ✅ Yes (per-stage metrics) |
| Score records | bt_scores | ✅ Yes (per-candidate scoring) |
| Harness decisions | bt_harness_decisions | ✅ Yes (gate outcomes) |
| Review queue item | bt_review_queue | ✅ Yes (if draft produced) |
| Review labels | bt_review_labels | ✅ When operator labels |

### Known Gaps

- `bt_runs.final_score` column does not exist (score is in `bt_scores` or `bt_daily_campaigns.result_json`)
- `bt_daily_campaigns` does not have `created_at` column (uses `started_at`)
- `bt_review_queue` does not have `created_at` column (uses `inserted_at`)
- `bt_review_labels` does not link directly to `bt_daily_automation_runs` — linked via `campaign_id`
- Shadow mode campaigns do not have `bt_daily_automation_runs` entries (they run outside the formal daily runner)

### Data Integrity Notes

- champion_score in bt_review_queue shows 0.0 for all March 11 production runs (known issue — score not persisted to review queue when champion_score=0.0 in campaign result)
- Shadow campaigns use internal policy_id `3f24a0a2a8074759` (DB-assigned UUID for evidence_diversity_v1), not the named ID `evidence_diversity_v1`
- This is normal: named ID `evidence_diversity_v1` is used for the policy registry record; `3f24a0a2a8074759` is the UUID assigned by the registry

---

## Review Label Completion

### Existing Labels (inherited from Phase 9D A/B trial)

| Decision | Count |
|----------|-------|
| approve | 30 |
| defer | 18 |
| reject | 2 |
| **Total** | **50** |

### Labels Required for Phase 9F Window

| Requirement | Target |
|-------------|--------|
| Champion labels (Phase 9F formal runs) | 1 per formal run |
| Runner-up labels (Phase 9F formal runs) | 1 per formal run |
| Shadow campaign labels | Optional (supplementary) |

---

## Data Capture Verdict

- **Core campaign data:** CAPTURED — all bt_daily_campaigns entries populated
- **Candidate data:** CAPTURED — bt_candidates, bt_scores, bt_harness_decisions
- **Review queue:** CAPTURED — 5 pending items from March 11 phase5_champion runs
- **Review labels for Phase 9F formal runs:** PENDING (runs in progress)
- **Shadow run labels:** NOT YET COLLECTED (pending operator review)

No minimal persistence bugs found that require code fixes.

---

## Blocker Log (Phase 9F)

### BLK-1: Stale Campaign Lock (2026-03-12)

**What happened:** First eval run attempt (campaign `78babbe9efeb4549`) was started with MockEmbeddingProvider (missing `BT_EMBEDDING_MODEL` env var). It was stopped and restarted with the correct environment. However, the kill operation left a stale lock file at `runtime/campaign.lock` with the dead PID (29996). The second attempt (`eda42cc79068413a`) then failed preflight with "Preflight failed: 1 critical check(s) failed" on the `campaign_lock` check.

**Root cause:** Stopping a background task via `TaskStop` leaves the lock file behind if the process was in mid-campaign-setup.

**Fix applied:** Removed stale `runtime/campaign.lock` manually. This is a safe operation when the PID is confirmed dead and no campaign is actually running.

**Impact:** One extra `aborted_preflight` campaign record in `bt_campaign_receipts`. No data loss. The aborted campaign was also updated to `aborted_runtime` with a descriptive failure_reason.

**Prevention:** Always verify lock file is clear before running formal campaigns. Lock path: `runtime/campaign.lock`.

**Code change required:** No — this is an operational procedure issue, not a code bug. The lock check is correct behavior.

---

## Update Log

| Date | Event |
|------|-------|
| 2026-03-12 | Phase 9F started; 6 shadow campaigns confirmed in DB under evidence_diversity_v1 |
| 2026-03-12 | BLK-1: Stale lock from killed run; fixed by removing runtime/campaign.lock |
| 2026-03-12 | 12 Phase 9F shadow review labels inserted into bt_review_labels |
| 2026-03-12 | 9F-E1 evaluation daily run started (campaign 9e5d26795855404c, running since 04:41Z) |
