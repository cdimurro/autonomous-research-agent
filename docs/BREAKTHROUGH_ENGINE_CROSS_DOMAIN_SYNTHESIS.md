# Breakthrough Engine - Cross-Domain Synthesis

## Phase 5 addition

Generates hybrid hypotheses that intentionally bridge two domains, with proper evidence assembly, fit scoring, and novelty evaluation.

## Problem Solved

Single-domain generation produces excellent candidates within one field, but misses opportunities at domain boundaries. Cross-domain synthesis targets the intersection of two domains (e.g., materials science techniques applied to clean-energy problems) where breakthrough potential is highest.

## Architecture

### SynthesisContext

```python
@dataclass
class SynthesisContext:
    run_id: str
    primary_domain: str          # e.g. "clean-energy"
    secondary_domain: str        # e.g. "materials"
    primary_sub_domain: str      # e.g. "green hydrogen production"
    secondary_sub_domain: str    # e.g. "catalytic materials"
    bridge_mechanism: str        # e.g. "catalyst design for electrolysis"
    pairing_policy: str          # "fixed_pair" | "rotating_pair" | "weighted_pair"
    excluded_cross_themes: list[str]  # previously tried cross-domain themes
```

### Domain Pair Policies

| Policy | Behavior |
|--------|----------|
| `fixed_pair` | Always uses the same domain pair |
| `rotating_pair` | Rotates through sub-domain combinations |
| `weighted_pair` | Selects pairs weighted by unexplored potential |

### SynthesisFitEvaluator

Scores cross-domain candidates on:
- `cross_domain_fit_score` — overall synthesis quality
- `bridge_mechanism_score` — strength of the bridging mechanism
- `evidence_balance_score` — balance between primary/secondary evidence
- `superficial_mashup_flag` — detects weak combinations

### Evidence Role Tagging

Evidence items in synthesis packs are tagged:
- `primary_support` — evidence from primary domain
- `secondary_support` — evidence from secondary domain
- `bridge_support` — evidence supporting the bridging mechanism

### Synthesis-Aware Novelty

Novelty evaluation extended to check:
- Prior same-pair hybrids
- Prior single-domain neighbors from either side
- Bridge-mechanism similarity

Diagnostics show whether conflict came from primary, secondary, or hybrid prior art.

## Integration Points

- **Orchestrator**: Detects cross-domain programs, builds SynthesisContext, uses it alongside DiversityContext
- **CandidateGenerator**: Receives synthesis prompt addendum with bridge instructions
- **EvidenceAssembly**: Gathers evidence from both domains, tags by role
- **NoveltyEngine**: Extended for cross-domain prior art
- **Scoring**: Synthesis fit bonus/penalty in final score
- **Review**: Synthesis metadata visible in drafts

## Cross-Domain Sub-Domains

Bridge sub-domains connecting clean-energy and materials:
1. electrocatalysts for energy conversion
2. advanced membranes for fuel cells
3. thermoelectric materials for waste heat
4. photovoltaic absorber materials
5. battery electrode materials
6. hydrogen storage materials
7. thermal insulation materials
8. corrosion-resistant coatings for offshore energy
9. superconducting materials for grid
10. phase-change materials for thermal storage
