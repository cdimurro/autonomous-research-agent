# Breakthrough Engine - Diversity Engine

## Phase 4D addition

Solves novelty saturation by steering generation away from already-explored semantic space.

## Problem Solved

After 120+ production runs in clean-energy, 90% of new candidates are blocked by the embedding novelty gate. Thresholds are correct — the space is genuinely saturated. The fix: steer generation toward unexplored sub-domains rather than loosening novelty checks.

## Components

### `breakthrough_engine/diversity.py`

**`DiversityContext`**
```python
@dataclass
class DiversityContext:
    run_id: str
    domain: str
    sub_domain: str = ""          # e.g. "solar photovoltaics"
    excluded_topics: list[str]    # phrases from recently-blocked candidates
    excluded_neighbor_titles: list[str]  # titles that appeared as nearest neighbors
    rotation_policy: str = "auto"  # "auto" | "fixed" | "random"
    focus_areas: list[str]        # specific angles within sub-domain
```

**`DiversityEngine`**
```python
engine = DiversityEngine(repo)
ctx = engine.build_context(run_id, domain)  # builds from DB state
engine.advance_rotation(domain)             # called after run completes
```

**`build_diversity_prompt_addendum(ctx)`**
Returns a string appended to the evidence block before LLM generation:
```
DIVERSITY CONSTRAINTS (apply these to all hypotheses):
SUB-DOMAIN FOCUS: solar photovoltaics
  All hypotheses must be specifically relevant to solar photovoltaics...
AVOID THESE OVER-EXPLORED TOPICS: perovskite coating; tandem cell; AEM electrolyzer
  These topics are saturated in our corpus...
DO NOT REPRODUCE OR CLOSELY PARAPHRASE: ...
PREFERRED FOCUS AREAS: carrier recombination reduction, stability under illumination
```

### `breakthrough_engine/corpus_manager.py`

**`CorpusManager`**
- `is_active(candidate_id)` → bool
- `run_archival(domain)` → stats dict (archived by age)
- `archive_by_cluster(domain, cluster_candidates, cluster_id, keep_newest=5)` → int
- `get_active_count(domain)` → int
- `get_active_candidate_ids(domain, limit=200)` → set[str]

Archival is additive: archived candidates stay in DB, just excluded from corpus. Published/draft_pending_review candidates are never archived.

## Sub-Domain Rotation

Each domain has 10 sub-domains defined in its YAML config (`sub_domains` field):

**clean-energy sub-domains:**
1. solar photovoltaics
2. grid-scale energy storage
3. green hydrogen production
4. wind energy systems
5. carbon capture and utilization
6. thermal energy storage
7. fuel cells and electrolyzers
8. building energy efficiency
9. offshore energy systems
10. bioenergy and biomass

**materials sub-domains:**
1. two-dimensional materials
2. metal-organic frameworks
3. high-entropy alloys
4. biomaterials and hydrogels
5. quantum materials
6. polymer nanocomposites
7. self-healing materials
8. additive manufacturing materials
9. catalytic materials
10. optical and photonic materials

Sub-domain rotates every `SUB_DOMAIN_ROTATION_INTERVAL = 2` runs, persisted in `bt_rotation_state`.

## Schema v005 Tables

| Table | Purpose |
|-------|---------|
| `bt_diversity_context` | Per-run diversity parameters (run_id, domain, sub_domain, excluded lists) |
| `bt_rotation_state` | Per-domain rotation state (domain PK, last_sub_domain, index, total_runs) |
| `bt_corpus_archive` | Archived candidate IDs (candidate_id PK, domain, reason, cluster_id) |

## Integration Points

- **Orchestrator**: `build_context()` before generation, `advance_rotation()` after run
- **OllamaCandidateGenerator**: `generate(..., diversity_context=ctx)` appends addendum to user message
- **FakeCandidateGenerator** / **DemoCandidateGenerator**: accept `diversity_context` parameter (ignored)
- **BenchmarkCandidateGenerator**: also accepts parameter (ignored)

## Negative Memory Extraction

`DiversityEngine._extract_excluded_topics()` queries recent `novelty_failed`, `dedup_rejected`, and other failed candidates in the domain. Their titles are processed by `_extract_title_topics()` which:
1. Filters stop words ("a", "the", "novel", "enhanced", etc.)
2. Extracts 2-gram noun phrases
3. Returns up to 3 topics per title, capped at 15 total

These become the "AVOID" list in the prompt addendum.

## Expected Impact

- Sub-domain steering pushes generation into unexplored corners of the semantic space
- Negative memory prevents repeated near-duplicate titles
- Corpus archival (future runs) will compress the active comparison set
- Net result: higher novelty gate pass rate without changing thresholds
