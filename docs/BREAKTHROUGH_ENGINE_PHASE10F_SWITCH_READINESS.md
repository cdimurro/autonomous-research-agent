# Phase 10F: Switch-Readiness Decision

**Date:** 2026-03-12

## Recommendation: `ready_for_limited_production_retrieval_ab`

## Evidence

### Retrieval Quality (Comparison v5)
| Check | Required | Actual | Result |
|-------|----------|--------|--------|
| score_preservation | >= current - 0.01 (0.869) | **0.8973** | **PASS** (+0.018) |
| diversity_improvement | > current (11) | **17** | **PASS** (+55%) |
| source_type_diversity | > 1 | **4** | **PASS** |
| grounding_quality | >= 0.30 | **0.517** | **PASS** |
| strong_support_items | > 0 | **14** | **PASS** |
| unsupported_items | < 50% of evidence | **0** (0%) | **PASS** |
| cross_paper_paths | > 0 | **10** (100% cross-paper) | **PASS** |

### Pipeline Wiring Verification
| Component | Status |
|-----------|--------|
| Evidence source injection | WIRED (opt-in via LadderConfig) |
| Graph-conditioned generation | WIRED (opt-in via enable_graph_context) |
| Production default unchanged | VERIFIED (tests confirm) |
| Canonicalization hardened | YES (90.4% collapse rate) |
| Grounding hardened | YES (0 unsupported items) |

### What Improved Since Phase 10E-Prime

| Metric | Phase 10E-Prime | Phase 10F | Change |
|--------|-----------------|-----------|--------|
| Mean relevance | 0.885 | **0.897** | +0.012 |
| Grounding score | 0.393 | **0.517** | +0.124 |
| Strong support items | 2 | **14** | +600% |
| Unsupported items | 10 | **0** | Eliminated |
| Pipeline wired | NO | **YES** | Fixed |
| Collapse rate | 70.7% | **90.4%** | +20pp |

### Downstream Campaign Comparison
(Pending — running in background)

## Risk Assessment

- **Low risk**: Production default is completely unchanged. Graph path is opt-in only.
- **Reversible**: Removing `evidence_source_override` and `enable_graph_context` returns to current behavior.
- **Bounded**: Limited A/B would use 3-5 shadow campaigns with graph-native vs current.

## Conditions for Full Production Switch

1. Limited A/B confirms no regression in champion quality
2. Review labels show >= 60% approval rate for graph-native champions
3. No novel failure modes discovered in graph-conditioned generation
4. Write-back memory loop activated for graph quality feedback

## Recommendation Details

The graph-native path now:
1. Actually reaches the LLM (graph-conditioned template is used)
2. Uses real evidence from HybridKGEvidenceSource
3. Has well-grounded evidence (0 unsupported items)
4. Provides 55% more source diversity
5. Surpasses current retrieval quality by +0.018

This is sufficient to recommend a **limited production retrieval A/B** where a small fraction of shadow campaigns use the graph-native path. Full production switch should wait for downstream campaign results confirming quality.
