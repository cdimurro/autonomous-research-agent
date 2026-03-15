# Breakthrough Engine — Project Summary

**Last Updated:** 2026-03-14
**Branch:** `breakthrough-engine-phase10k-graph-native-rollout`
**Current Phase:** 10K (Graph-Native Retrieval Promotion — COMPLETE)
**Champion Policy:** `evidence_diversity_v1`
**Default Retrieval:** `HybridKGEvidenceSource` (graph-native, promoted Phase 10K)
**Test Suite:** 1171 passing, 0 failures
**Production Mean Score:** 0.9108 (100% approval across 6 burn-in campaigns)
**Adoption Decision:** `ready_to_merge_and_adopt`
**Repository:** `https://github.com/cdimurro/breakthrough-engine.git`

---

## 1. What Is the Breakthrough Engine?

The Breakthrough Engine is an automated scientific hypothesis generation and evaluation system. It ingests published research findings, identifies cross-domain connections, generates novel research hypotheses, scores them across multiple quality dimensions, and selects champions through a rigorous multi-stage pipeline.

The system operates on a daily cycle: it gathers evidence from scientific papers and knowledge graphs, generates candidate hypotheses using a local LLM (Ollama), filters them through deterministic quality gates, scores survivors, and selects a daily champion. A policy system enables A/B testing of different generation and scoring strategies, with formal promotion and rollback guardrails.

**Domain focus:** Clean energy and advanced materials, with cross-domain synthesis (e.g., materials innovations applicable to energy systems).

**Key outputs:** Ranked, scored research hypotheses with evidence backing, novelty verification, and domain-fit evaluation.

---

## 2. Architecture Overview

### 2.1 Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.14 |
| Data modeling | Pydantic v2 |
| Database | SQLite (`runtime/db/scires.db`) |
| LLM (generation) | Ollama — `qwen3.5:9b-q4_K_M` |
| Embeddings | Ollama — `qwen3-embedding:4b` (2560-dim, Regime 2) |
| External APIs | Semantic Scholar, OpenAlex, Crossref, AlphaXiv |
| Testing | pytest (1171 tests, all offline-safe) |

### 2.2 Module Map (45 Python Modules)

```
breakthrough_engine/
├── Core Infrastructure
│   ├── models.py           # Pydantic domain models, lifecycle enums
│   ├── db.py               # SQLite schema (65+ tables), Repository (50+ methods)
│   ├── config_loader.py    # YAML research program loader
│   └── memory.py           # Cross-run duplicate detection
│
├── Orchestration & Execution
│   ├── orchestrator.py     # 10-step daily pipeline (1700+ lines)
│   ├── daily_search.py     # 5-stage quality-first campaign ladder
│   ├── campaign_manager.py # Campaign execution + receipt tracking + graph-native wiring
│   └── daily_automation.py # Production automation entry points
│
├── Candidate Generation
│   └── candidate_generator.py  # Fake/Demo/Ollama generator providers
│
├── Evidence & Retrieval
│   ├── evidence_source.py     # EvidenceSource ABC, ExistingFindingsSource
│   ├── retrieval.py           # S2, OpenAlex, rank_evidence(), CompositeSource
│   ├── hybrid_retrieval.py    # HybridKGEvidenceSource (trusted + KG mixing)
│   ├── kg_retrieval.py        # KGEvidenceSource (KG-backed retrieval)
│   └── kg_calibration.py      # KG evidence confidence calibration
│
├── Knowledge Graph (Phase 10A+)
│   ├── paper_ingestion.py     # Paper segmentation + relevance scoring
│   ├── kg_extractor.py        # LLM entity/relation extraction
│   ├── kg_reasoning.py        # Multi-hop reasoning, path finding (600+ lines)
│   ├── kg_canonicalization.py # Entity deduplication + canonical names
│   ├── kg_comparison.py       # KG vs production retrieval comparison
│   ├── kg_writer.py           # Write-back findings to KG tables
│   ├── kg_grounding.py        # Graph-based plausibility scoring
│   ├── kg_segment_scorer.py   # Segment relevance scoring
│   └── kg_subgraph.py         # Subgraph extraction + analysis
│
├── Scoring & Evaluation
│   ├── scoring.py             # 7-dimension scoring, weighted formula
│   ├── novelty.py             # Embedding + lexical novelty detection
│   ├── domain_fit.py          # Cross-domain suitability
│   ├── harnesses.py           # 4 deterministic gates (no LLM)
│   ├── falsification.py       # Adversarial stress-testing
│   └── bayesian_evaluator.py  # Posterior estimation for policy trials
│
├── Diversity & Synthesis
│   ├── diversity.py           # Sub-domain rotation, excluded topics
│   └── synthesis.py           # Cross-domain bridge synthesis
│
├── Policy & Baselines
│   ├── policy_registry.py     # Champion/challenger tracking, promotion model
│   ├── challenger_trial.py    # A/B trial execution
│   ├── reviewed_baseline.py   # Label-driven policy updates
│   ├── review_cockpit.py      # Operator review workflow
│   └── baseline_comparator.py # Benchmark comparison to frozen baselines
│
├── Monitoring & Observability
│   ├── embeddings.py          # Embedding provider abstraction
│   ├── embedding_monitor.py   # Embedding diversity tracking
│   ├── reward_logger.py       # Reward signal logging
│   ├── label_completeness.py  # Review label analysis
│   └── notifications.py      # Async notification dispatch
│
├── API & CLI
│   ├── api.py                 # Flask REST API (20+ routes)
│   └── cli.py                 # CLI entrypoints (20+ subcommands)
│
└── Utilities
    ├── corpus_manager.py      # Corpus aging + archival
    ├── simulator.py           # Simulator adapter abstraction
    ├── review.py              # Publication draft creation
    ├── reporting.py           # JSON + Markdown report generation
    ├── bootstrap_findings.py  # Batch findings ingestion
    ├── scheduler.py           # Cron-based scheduling (launchd)
    └── preflight.py           # Pre-run health checks
```

---

## 3. The Pipeline: How a Hypothesis Is Born

Each daily run executes the following 10-step pipeline in `orchestrator.py`:

### Step 1: Gather Evidence
The system collects evidence from configured sources. With graph-native retrieval (Phase 10K default), this uses `HybridKGEvidenceSource` which combines `ExistingFindingsSource` (trusted database findings) with `KGEvidenceSource` (knowledge graph segments, entities, relations). Source-aware pool construction (Phase 10J) ensures diversity via `min_kg_items=2` and `max_per_paper=3`.

For cross-domain programs, evidence is gathered from both primary (clean-energy) and secondary (materials) domains.

**Evidence diversity check (Phase 10J):** When the generator's `evidence_refs` match items that all share the same `source_id`, the orchestrator falls through to `rank_evidence()` + `select_diverse_top_k()` instead of using the non-diverse matched items directly.

### Step 2: Corpus Maintenance
`CorpusManager` ages out stale candidates from the corpus to prevent novelty saturation. Archive threshold is configurable per domain.

### Step 3: Generate Candidates
The `DiversityEngine` builds a context with sub-domain focus, excluded topics (from recent failures), and rotation policy. The `SynthesisEngine` selects a cross-domain bridge mechanism (e.g., "electrocatalysts for energy conversion").

These contexts are formatted into prompt addenda and passed to `OllamaCandidateGenerator`, which calls the local Ollama instance with `qwen3.5:9b-q4_K_M` to generate ~7-8 candidate hypotheses per run.

Each candidate has: title, statement, mechanism, expected_outcome, testability_window_hours, novelty_notes, assumptions, risk_flags, and evidence_refs.

### Step 4: Filtering Gates
Candidates pass through a series of deterministic gates (no LLM calls):

1. **Hypothesis Legality Harness** — Checks statement specificity, mechanism detail, expected outcome clarity
2. **Deduplication** — Embedding similarity against all prior candidates using `EmbeddingNoveltyEngine`
3. **Evidence Assembly** — `rank_evidence()` selects top items by mechanism relevance (using policy-configured weights)
4. **Evidence Legality Harness** — Validates evidence count, diversity, provenance
5. **Domain Fit** — Cross-domain transfer likelihood scoring
6. **Synthesis Fit** — Bridge mechanism validation (genuine cross-domain connection vs shallow mashup)
7. **Novelty Gate** — Embedding-based prior art detection, duplicate risk scoring

Typically ~3 candidates survive as finalists; the rest are rejected with specific reasons.

### Step 5: Simulation
Simulation specs are generated for top finalists. The `MockSimulatorAdapter` (or `OmniverseSimulatorAdapter` when available) runs feasibility simulations. Results include key metrics, pass/fail summary, and confidence scores.

### Step 6: Scoring & Ranking
Each finalist is scored across 7 dimensions:

| Dimension | Weight | Signal Source |
|-----------|--------|--------------|
| Novelty | 0.20 | novelty_notes length, harness pass ratio |
| Plausibility | 0.20 | mechanism detail, risk flag count |
| Impact | 0.20 | expected_outcome detail |
| Evidence Strength | 0.20 | item count, source diversity, trust weighting |
| Simulation Readiness | 0.10 | simulation result status |
| Inverse Validation Cost | 0.10 | testability_window_hours |

The `evidence_strength_score` uses source-type-aware trust weighting (finding: 1.0, paper: 0.95, kg_segment: 0.85, kg_graph: 0.80) with diversity bonuses for unique source_ids and source_types.

Weights can be overridden by the active policy's `scoring_weights`.

### Step 7: Publication Gate
Checks: score >= threshold, evidence attached, assumptions disclosed. Only candidates passing the gate are eligible for publication.

### Step 8: Publication / Draft / Shadow
Depending on run mode:
- **Auto-publish** (deterministic_test, demo_local, production_local): Creates `PublicationRecord`
- **Review** (production_review): Creates `PublicationDraft` for operator approval
- **Shadow** (production_shadow): No output, used for A/B trials

### Step 9: Metrics & Notifications
Saves run metrics, advances diversity/synthesis rotations, logs reward signals, dispatches notifications.

### Step 10: Post-Run
Updates corpus embedding monitor, returns completed `RunRecord`.

---

## 4. The Campaign System

The `DailySearchLadder` wraps the orchestrator pipeline into a 5-stage quality-first campaign:

**Stage 1: Broad Exploration** — Runs multiple orchestrator cycles (up to 3 trials or wall-clock limit), collecting all finalists. Stops early if posterior dominance is detected.

**Stage 2: Shortlist** — Filters by minimum score, takes top-K (default 3) by `final_score`.

**Stage 3: Falsification** — `FalsificationEngine` stress-tests shortlisted candidates with adversarial prompts. Measures vulnerabilities and survivability.

**Stage 4: Review Packet Prep** — `ReviewCockpit` formats survivors into decision packets for operator review or automated labeling.

**Stage 5: Champion Selection** — Selects best survivor by `final_score`. Archives non-champions.

Output: `DailyCampaignResult` with campaign_id, champion, ladder_stages, and review packets.

**Two modes:**
- `benchmark` — Fixed budgets, offline-safe, for policy comparison
- `production` — Wall-clock budget (120 min), real LLM + embeddings

---

## 5. The Policy System

### 5.1 What Policies Control

A `PolicyConfig` defines tunable surfaces that affect hypothesis quality:

| Surface | What It Controls | Status |
|---------|-----------------|--------|
| `scoring_weights` | Weight allocation across 7 scoring dimensions | WIRED |
| `generation_prompt_variant` | LLM prompt template ("standard", "synthesis_focus") | WIRED |
| `evidence_ranking_weights` | How evidence items are ranked for inclusion | WIRED |
| `sub_domain_rotation_policy` | Sub-domain cycling strategy | WIRED |
| `diversity_steering_variant` | Generation diversity aggressiveness | DEFERRED |
| `negative_memory_strategy` | How past failures inform future runs | DEFERRED |
| `bridge_selection_policy` | Cross-domain bridge mechanism selection | DEFERRED |

### 5.2 Promotion Model

Policies follow a champion/challenger lifecycle:

```
Register challenger → A/B trial (6+6 campaigns) → Manual promotion decision
                                                 → Rollback if quality degrades
```

**Promotion requires ALL thresholds to pass:**
- Score preservation: challenger >= champion - 0.01
- Approval rate >= 60%
- Diversity >= current
- No systematic failures (<= 1)
- Score above rollback threshold (>= -0.05)
- Approval above rollback threshold (>= 40%)

**Rollback triggers (mandatory):**
- Approval rate < 40% over 6 consecutive runs
- Score regression > 0.05 vs frozen baseline

### 5.3 Policy History

| Policy | Outcome | Root Cause |
|--------|---------|-----------|
| `phase5_champion` | Archived (was champion) | Baseline; replaced by evidence_diversity_v1 |
| `synthesis_focus_v1` | RETIRED_FAILED | Prompt suppressed novelty; scoring penalized novelty |
| `evidence_diversity_v1` | **CHAMPION** (since 2026-03-12) | Mechanism-aligned evidence → better grounding |

### 5.4 Current Champion: `evidence_diversity_v1`

```json
{
  "evidence_ranking_weights": {
    "api_relevance": 0.20,
    "domain_overlap": 0.30,
    "mechanism_overlap": 0.35,
    "baseline": 0.15
  }
}
```

Key insight: Increasing `mechanism_overlap` from 0.20 to 0.35 (+75%) and decreasing `api_relevance` from 0.35 to 0.20 produced better-grounded hypotheses with higher plausibility scores.

---

## 6. The Knowledge Graph System (Phase 10A+)

### 6.1 Data Flow

```
Published Papers
    ↓
Paper Ingestion (paper_ingestion.py)
    → segment_text() splits papers into ~1000-char segments
    → SegmentRelevanceScorer scores relevance via embedding similarity
    → Writes to bt_paper_segments
    ↓
Entity/Relation Extraction (kg_extractor.py)
    → LLM extracts entities (material, mechanism, process, etc.)
    → LLM extracts relations (causes, enhances, composed_of, etc.)
    → Writes to bt_kg_entities, bt_kg_relations
    ↓
Graph Reasoning (kg_reasoning.py)
    → KGGraphBuilder constructs directed graph
    → MultiHopReasoner finds paths between concepts
    → CrossPaperSynthesizer discovers cross-domain bridges
    ↓
Evidence Retrieval (kg_retrieval.py, hybrid_retrieval.py)
    → KGEvidenceSource gathers items from KG tables
    → HybridKGEvidenceSource mixes trusted + KG evidence
    → Evidence calibration adjusts KG confidence levels
    → Source-aware pool construction (Phase 10J)
    ↓
Graph-Conditioned Generation (orchestrator.py)
    → _build_graph_context() constructs reasoning context
    → GRAPH_CONDITIONED_TEMPLATE replaces flat evidence template
    → Candidates generated with structural knowledge
```

### 6.2 Entity and Relation Types

**Entity types:** material, compound, mechanism, process, property, organism, gene, protein, device, method, concept, metric, phenomenon, structure, technology

**Relation types:** causes, inhibits, enhances, composed_of, measured_by, used_in, produces, degrades, catalyzes, related_to, enables, requires, competes_with, analog_of

### 6.3 Graph Caching (Phase 10H)

The `_build_graph_context()` method caches expensive operations:
- **Cached** (keyed by domain + entity/relation counts): canonical map, graph structure, reasoning paths
- **Per-run** (evidence-dependent): topic subgraph extraction

Cache hit rate: ~95% within a daily campaign cycle. First run pays full cost; subsequent runs skip canonicalization, graph building, and path finding. Result: 18% elapsed time reduction in Phase 10H A/B.

### 6.4 Current KG State

| Metric | Count |
|--------|-------|
| Paper segments | ~370 |
| KG entities | ~1726 |
| KG relations | ~1179 |
| Findings (accepted) | 53 from 24 papers |

---

## 7. The Evidence System

### 7.1 Evidence Sources

| Source | Type | Used In |
|--------|------|---------|
| `ExistingFindingsSource` | Trusted DB findings | Component of HybridKGEvidenceSource |
| `KGEvidenceSource` | KG tables | Component of HybridKGEvidenceSource |
| `HybridKGEvidenceSource` | Trusted + KG mix | **Production default (Phase 10K)** |
| `SemanticScholarRetrievalSource` | Live API | Available via CompositeRetrievalSource |
| `OpenAlexRetrievalSource` | Live API | Available via CompositeRetrievalSource |
| `DemoFixtureSource` | 6 hardcoded items | Testing only |

### 7.2 HybridKGEvidenceSource Configuration (Phase 10K Default)

```python
HybridKGEvidenceSource(
    trusted_source=ExistingFindingsSource(db),
    kg_source=KGEvidenceSource(repo),
    min_trusted_quota=12,
    kg_diversification_quota=8,
    min_kg_items=2,       # Reserve slots for KG items
    max_per_paper=3,      # Cap per-source concentration
)
```

Key Phase 10J fixes active in production:
- **evidence_refs diversity fallthrough**: When matched items have fewer unique sources than top_k, falls through to ranked matching
- **Source-aware hybrid pool**: `min_kg_items=2` reserves KG slots, `max_per_paper=3` prevents single-paper domination
- **`_select_diverse_kg()`**: Prefers KG items from distinct sources

### 7.3 Evidence Ranking

`rank_evidence()` scores items using a weighted composite:

| Weight | evidence_diversity_v1 | Default |
|--------|----------------------|---------|
| mechanism_overlap | **0.35** | 0.20 |
| domain_overlap | 0.30 | 0.30 |
| api_relevance | 0.20 | 0.35 |
| baseline | 0.15 | 0.15 |

Each candidate's evidence pack contains the top-ranked items (minimum 2). The `source_diversity_count` on each pack tracks unique source_ids.

### 7.4 Evidence Strength Scoring

Source-type-aware trust weighting:

| Source Type | Trust Weight |
|-------------|-------------|
| finding | 1.00 |
| paper | 0.95 |
| journal | 0.95 |
| kg_segment | 0.85 |
| kg_graph | 0.80 |
| graph_path | 0.75 |
| kg_subgraph | 0.72 |
| kg_synthesis | 0.70 |

Formula: `evidence_strength = min(1.0, avg(relevance * trust) * count_penalty + diversity_bonus)`

---

## 8. Diversity & Synthesis

### 8.1 Diversity Engine

The `DiversityEngine` prevents topic saturation by:

1. **Sub-domain rotation** — Cycles through ~10 sub-domains per domain every 2 runs (e.g., solar photovoltaics → grid storage → green hydrogen → ...)
2. **Excluded topics** — Extracts noun phrases from recently rejected candidates (novelty_failed, dedup_rejected) and tells the generator to avoid them
3. **Excluded neighbor titles** — Prevents reproduction of specific prior hypotheses

### 8.2 Synthesis Engine

For cross-domain programs (clean-energy + materials), the `SynthesisEngine`:

1. Selects a bridge mechanism from 10 predefined bridges (e.g., "electrocatalysts for energy conversion", "thermoelectric materials for waste heat")
2. Rotates bridge selection every 2 runs
3. `SynthesisFitEvaluator` validates that candidates genuinely bridge domains (not shallow mashups)

---

## 9. Database Schema

The system uses 65+ SQLite tables, all prefixed with `bt_` to coexist with the upstream `scires.db` schema.

### Core Tables
- `bt_runs` — Run records (program, mode, status, timestamps)
- `bt_candidates` — All candidates (title, mechanism, status, rejection_reason)
- `bt_scores` — 7-dimension scoring breakdowns
- `bt_publications` — Published candidates (one per run max)
- `bt_evidence_packs` — Evidence pack metadata + source_diversity_count
- `bt_evidence_items` — Individual evidence items per pack

### Policy & Trial Tables
- `bt_policies` — Policy configurations + state (champion/challenger/rolled_back)
- `bt_policy_trials` — Trial history with metrics and outcomes
- `bt_policy_promotion_log` — Promotion/rollback events
- `bt_bayesian_posteriors` — Posterior estimates per metric

### Knowledge Graph Tables
- `bt_paper_segments` — Segmented papers with relevance scores
- `bt_kg_entities` — Extracted entities (type, name, confidence, domain)
- `bt_kg_relations` — Extracted relations (source→target, type, confidence)
- `bt_kg_findings` — Write-back findings with temporal versioning

### Campaign Tables
- `bt_daily_campaigns` — Campaign results with config and champion
- `bt_ladder_stages` — 5-stage ladder results
- `bt_campaign_receipts` — Execution receipts with finalists
- `bt_review_labels` — Operator/automated review labels

### Current count: 124+ review labels in DB

---

## 10. Embedding Regime Boundary

**Critical context for interpreting historical data:**

| Regime | Model | Dimensions | Commits |
|--------|-------|-----------|---------|
| Regime 1 (OLD) | `nomic-embed-text` | 768 | Up to `1b52a0f` (Phase 8B) |
| Regime 2 (NEW) | `qwen3-embedding:4b` | 2560 | `bbd7692` (Phase 9) onward |

Baselines from Regime 1 (phase7d, phase8) are **not comparable** to Regime 2 runs. The boundary commit is `bbd7692`. All current production baselines use Regime 2.

---

## 11. Phase History and Results

### Phase 1-5: Foundation (complete)
- Basic pipeline, scoring formula, cross-domain synthesis, policy system
- `phase5_champion` established as first production policy

### Phase 6: Daily Search Ladder (complete)
- 5-stage quality-first campaign system
- Baseline comparison framework

### Phase 7A-D: Embedding & Evaluation (complete)
- Embedding novelty engine, evaluation packs, production regime
- Established Regime 1 baselines

### Phase 8B: Challenger Trial Framework (complete)
- A/B trial execution, baseline freeze, daily automation
- Policy promotion/rollback CLI commands

### Phase 9: Policy A/B Trials (complete)

| Trial | Challenger | Score Delta | Approval | Verdict |
|-------|-----------|------------|----------|---------|
| Phase 9B | synthesis_focus_v1 | -0.02 | 50% | PROMOTION_NOT_RECOMMENDED |
| Phase 9D | evidence_diversity_v1 | +0.01 | 83% | **PROMOTED** |

**evidence_diversity_v1** promoted as champion on 2026-03-12.

### Phase 9E: Promotion & Rollback Guardrails (complete)
- Manual promotion CLI, rollback triggers documented
- Regime 2 baseline frozen: mean 0.9126, 83.3% approval

### Phase 9F: Steady-State Operation (complete)
- 2 formal + 6 shadow runs, mean 0.9097, 100% approval
- All rollback triggers CLEAR
- 66 review labels (44 approve, 20 defer, 2 reject)

### Phase 10A: KG Shadow Foundation (complete)
- Paper ingestion, entity/relation extraction, shadow retrieval
- Comparison harness, write-back — 1015 tests

### Phase 10B-F: KG Integration Phases (complete)
- KG population, calibration, grounding, hybrid retrieval
- Graph-conditioned generation template
- Post-wiring shadow A/B confirmed both arms work

### Phase 10G: Limited Production Retrieval A/B — 6+6 (complete)

| Metric | Current | Graph Native | Delta |
|--------|---------|-------------|-------|
| Mean score | 0.9042 | **0.9079** | +0.004 |
| Approval | 100% | 100% | 0 |
| Diversity check | 2.0 | 1.0 | **FAIL** |

**Decision:** `continue_limited_ab` — Score/approval strong but diversity check failed.

### Phase 10H: Diversity Hardening + Extended A/B — 7+7 (complete)

**Code changes:**
1. Diversity fix (`kg_retrieval.py`): Changed KG segment source_ids from paper-level to segment-level
2. Graph caching (`orchestrator.py`): Module-level cache for canonical map, graph, paths (18% speedup)

| Metric | Current | Graph Native | Delta |
|--------|---------|-------------|-------|
| Mean score | 0.9084 | **0.9098** | +0.0014 |
| Diversity check | 2.0 | 1.0 | **FAIL** |

**Decision:** `continue_limited_ab` — Root cause: ranking layer narrows diversity, not a measurement artifact.

### Phase 10I: Diversity-Aware Ranking + Persistence Fix — 7+7 (complete)

**Code changes:**
1. Diversity-aware ranking in `select_diverse_top_k()`
2. Evidence item persistence fix (fresh IDs per pack)

| Metric | Current | Graph Native | Delta |
|--------|---------|-------------|-------|
| Mean score | 0.9005 | **0.9181** | +0.0176 |
| Unique sources | 2.0 | 1.0 | **FAIL** |
| Persistence | ~14% | 100% | Fixed |

**Decision:** `continue_limited_ab` — Persistence fixed but diversity still failing at the source.

### Phase 10J: Evidence_refs Diversity Fix + Source-Aware Pool — 7+7 (complete)

**Root cause discovered:** The generator sets `evidence_refs` on ALL candidates. When present, the orchestrator matches items directly, completely skipping `rank_evidence()` + `select_diverse_top_k()`. For graph-conditioned candidates, all refs pointed to items from a single paper.

**Code changes:**
1. **evidence_refs diversity fallthrough** (`orchestrator.py`): When matched items have fewer unique sources than top_k, fall through to ranked matching
2. **Source-aware hybrid pool** (`hybrid_retrieval.py`): `min_kg_items=2`, `max_per_paper=3`, `_select_diverse_kg()`

| Metric | Current | Graph Native | Delta |
|--------|---------|-------------|-------|
| Mean score | 0.9059 | **0.9163** | **+0.0104** |
| Approval | 100% | 100% | 0 |
| Unique sources | 2.0 | **8.7** | **+6.7** |
| Diversity score | 0.147 | **0.608** | **+0.461** |
| Persistence | 100% | 100% | 0 |
| **All 6 checks** | — | — | **PASS** |

**Decision:** `promote_graph_native_retrieval` — First time all checks pass across four A/B phases.

### Phase 10K: Graph-Native Retrieval Promotion + Burn-in (complete)

**Promotion:** `HybridKGEvidenceSource` wired as default retrieval in `campaign_manager.py`.

**Burn-in (3 eval + 3 prod):**

| Campaign | Profile | Champion | Score | Sources | Persistence |
|----------|---------|---------|-------|---------|-------------|
| 1 | eval | HEA-Based Thermal Conductivity Gradients | 0.8955 | 11 | 7/7 |
| 2 | eval | NiFe-LDH Anode Integration into ZIF-8 MOF | 0.8855 | 9 | 7/7 |
| 3 | eval | MXene-MOF Membrane Hybrids | 0.923 | 10 | 7/7 |
| 4 | prod | Topological Insulator Spin-Logic for Smart Grid | 0.8955 | 8 | 7/7 |
| 5 | prod | Ultrafast Ionic Transport for Dehumidified Insulation | 0.9324 | 5 | 7/7 |
| 6 | prod | Ultrafast Ion Transport Sensors for Corrosion Monitoring | 0.933 | 11 | 7/7 |

**Burn-in vs prior baseline:**

| Metric | Prior Baseline | Burn-in | Delta |
|--------|---------------|---------|-------|
| Mean score | 0.9126 | 0.9108 | -0.0018 |
| Approval | 83.3% | 100% | +16.7% |
| Unique sources | 2.0 | 9.0 | +7.0 |
| Persistence | — | 100% | — |

**All 6 health checks PASS. 12/12 labels approve. 0 failures.**
**Adoption decision: `ready_to_merge_and_adopt`**
**Baseline frozen: `phase10k_graph_native_production_regime2`**

### Phase-over-Phase Diversity Resolution

| Phase | Diversity Failure Layer | Fix |
|-------|----------------------|-----|
| 10G | Measurement (paper-level source_ids) | — |
| 10H | Ranking (top-k concentrates on one source) | segment-level source_ids |
| 10I | Evidence pool (KG corpus dominated by one paper) | diversity-aware ranking + persistence |
| **10J** | **evidence_refs bypass + pool construction** | **diversity fallthrough + source-aware pool** |

---

## 12. Current Baselines

| Baseline | Policy | Retrieval | Mean Score | Approval | Status |
|----------|--------|-----------|-----------|---------|--------|
| phase9c_operational_regime2 | phase5_champion | ExistingFindings | 0.905 | 66.7% | Archived |
| phase9e_promoted_production_regime2 | evidence_diversity_v1 | ExistingFindings | 0.9126 | 83.3% | Rollback anchor |
| **phase10k_graph_native_production_regime2** | **evidence_diversity_v1** | **HybridKGEvidenceSource** | **0.9108** | **100%** | **CURRENT** |

---

## 13. Rollback Path

If graph-native retrieval degrades after adoption:

### Rollback Triggers
| Trigger | Threshold | Action |
|---------|-----------|--------|
| Approval collapse | < 40% over 6 consecutive runs | Mandatory rollback |
| Score regression | < 0.85 mean (> -0.06 below baseline) | Mandatory rollback |
| Reject rate spike | >= 3/6 consecutive champions rejected | Mandatory rollback |
| Score delta < -0.05 sustained | Over 6 runs vs baseline | Mandatory rollback |

### Rollback Procedure (Option A: Code Reversion)
1. Remove `HybridKGEvidenceSource` construction block from `campaign_manager.py`
2. Remove `evidence_source_override=graph_native_source` from LadderConfig
3. Remove `enable_graph_context=True` from LadderConfig
4. Remove the 3 new imports

The orchestrator falls back to its default retrieval path (ExistingFindingsSource).

### Rollback Procedure (Option B: Branch Reversion)
```bash
git checkout breakthrough-engine-phase10g-retrieval-ab
```

Full details: `docs/BREAKTHROUGH_ENGINE_PHASE10K_ROLLBACK.md`

---

## 14. Post-Adoption Monitoring (14-Day Window)

For the first 7-14 days after adoption, monitor:
- Champion score per campaign (target: mean >= 0.88)
- Approval rate (target: >= 60%, rollback trigger: < 40%)
- Evidence diversity (target: >= 5 unique sources)
- Latency (baseline: ~891s per campaign)
- Label every champion and one runner-up

---

## 15. Known Issues and Next Steps

### Resolved Issues (Phase 10J/10K)
1. ~~Evidence ranking diversity gap~~ — Fixed by evidence_refs diversity fallthrough + source-aware pool
2. ~~Evidence item storage sparse~~ — Fixed by fresh IDs per pack (Phase 10I persistence fix)

### Remaining Issues
1. **Campaign lock** — Stale `runtime/campaign.lock` can persist from killed runs. Must be manually removed before subsequent runs.
2. **Graph context skipped** — KG canonicalization often produces 0 canonical concepts, causing graph context to be skipped. The system still works (falls back to flat evidence), but graph-conditioned generation is underutilized.

### Planned Next Steps
1. **PV Foundation Loop** (`pv-foundation-loop` batch) — First narrow-domain optimization loop for PV I-V characterization. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full design.
2. **Post-adoption monitoring** — 14-day observation window with labeling
3. **Battery domain pack** — Second domain loop (after PV is proven)
4. **DC-DC domain pack** — Third domain loop
5. **KG corpus expansion** — Ingest more papers to increase canonical concept coverage
6. **`diversity_steering_v1` challenger** — Next policy surface (design-only, not yet registered)

### Domain Rollout Order
1. **PV I-V Characterization** — In progress (pvlib-backed, fixed experiments, explicit metrics)
2. **Battery Characterization** — Planned
3. **DC-DC Converter Optimization** — Planned

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for architecture details and [docs/INDEX.md](docs/INDEX.md) for documentation navigation.

---

## 16. How to Run

### Prerequisites
```bash
# Ensure Ollama is running with required models
ollama list  # Should show qwen3.5:9b-q4_K_M and qwen3-embedding:4b

# Set environment
source .env  # Sets BT_EMBEDDING_MODEL and OLLAMA_MODEL
```

### Daily Operations
```bash
# Evaluation run (shadow mode, no publication)
python -m breakthrough_engine daily run evaluation_daily_clean_energy

# Production run
python -m breakthrough_engine daily run production_daily_clean_energy

# Batch collection (force mode)
python -m breakthrough_engine daily run evaluation_daily_clean_energy --force

# Dry run (preflight only)
python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy
```

### Policy Management
```bash
# List policies
python -m breakthrough_engine policy list

# Manual promotion
python -m breakthrough_engine policy manual-promote <policy_id> --reason "..." --trial-id <trial_id>

# Rollback
python -m breakthrough_engine policy rollback --reason "<reason>"
```

### Testing
```bash
PYTHONPATH=/Users/openclaw/breakthrough-engine .venv/bin/pytest tests/test_breakthrough/ -x -q
```

### Important Notes
- Always `source .env` before running — without it, `MockEmbeddingProvider` is used (wrong dimensions)
- Check `runtime/campaign.lock` doesn't exist before running (stale lock = preflight fail)
- Production DB is `runtime/db/scires.db` (not `runtime/bt_research.db` which is empty)
- Graph-native retrieval is now the production default via `campaign_manager.py`

---

## 17. File Organization

```
breakthrough-engine/
├── breakthrough_engine/     # 45 Python modules (source)
├── config/
│   ├── policies/            # Policy JSON configs
│   ├── research_programs/   # YAML program definitions
│   └── campaign_profiles/   # YAML campaign profiles
├── docs/                    # 150+ markdown docs (architecture, phases, decisions)
├── tests/
│   └── test_breakthrough/   # 32 test modules, 1171 tests
├── scripts/                 # Phase-specific execution scripts
├── runtime/                 # Mutable state (gitignored)
│   ├── db/scires.db         # Production SQLite database
│   ├── baselines/           # Frozen production baselines
│   ├── campaigns/           # Campaign artifacts
│   ├── phase9f/             # Steady-state production artifacts
│   ├── phase10g/            # Phase 10G A/B results
│   ├── phase10h/            # Phase 10H A/B results
│   ├── phase10j/            # Phase 10J A/B results
│   └── phase10k/            # Phase 10K burn-in results
├── .env                     # Local environment (gitignored)
├── .gitignore
└── project_summary.md       # This file
```

---

## 18. Constraints and Invariants

1. **One publication per run** — Each orchestrator cycle produces at most one published candidate
2. **Champion-only for production** — No challenger policies in production automation
3. **Offline-safe tests** — All 1171 tests run without network or LLM access
4. **Regime boundary** — Never compare Regime 1 baselines to Regime 2 runs
5. **Automatic promotion OFF** — All promotions require manual decision
6. **Rollback target** — Prior retrieval path (ExistingFindingsSource) via branch or code reversion
7. **Graph-native retrieval** — Production default since Phase 10K (`HybridKGEvidenceSource`)
