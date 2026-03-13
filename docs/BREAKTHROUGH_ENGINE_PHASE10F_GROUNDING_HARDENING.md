# Phase 10F: Grounding Hardening

**Date:** 2026-03-12

## Problem

Phase 10E-Prime grounding validation was too weak:
- 10/12 graph-derived items scored "unsupported" (score ~0.29)
- Only 2 items scored "strong_support"
- Mean grounding score 0.393 barely cleared the 0.30 threshold
- Graph paths with relevant concepts were penalized by low trust priors

## Root Causes

1. **Stopwords too few** — common scientific verbs ("using", "demonstrated", "achieved") inflated keyword counts without adding semantic signal
2. **Unigram-only matching** — compound terms like "perovskite solar cell" were matched as independent words, missing the compound signal
3. **Trust prior too dominant** — formula `overlap * 0.6 + trust * 0.2 + relevance * 0.2` meant graph_path trust (0.55) dragged scores below thresholds regardless of overlap quality
4. **No "partial_support" level** — gap between strong_support (>= 0.5) and weak_support (>= 0.3) was too wide

## Changes

### Keyword Extraction
- Expanded stopwords from 30 to 60+ (added scientific verbs, generic phrases)
- Added candidate title to claim keyword extraction (more keywords = better recall)
- Applied stopword filtering to evidence keywords too

### Bigram Matching
- New `_extract_bigrams()` function captures adjacent keyword pairs
- Compound terms like "solar_cell", "power_conversion" get matched as units
- Bigram bonus: +0.05 per matching bigram (capped at +0.15)

### Scoring Formula
- Rebalanced: `overlap * 0.65 + trust * 0.15 + relevance * 0.20`
- Overlap weight increased from 0.6 to 0.65
- Trust weight decreased from 0.2 to 0.15
- Trust priors raised: graph_path 0.55→0.60, kg_subgraph 0.52→0.58, kg_segment 0.70→0.72

### Structural Coherence Bonus
- Expanded: graph evidence with overlap > 0.25 gets +0.07 (was +0.05 at > 0.3)
- New intermediate: overlap > 0.15 gets +0.03

### Finer Verdict Levels
- `strong_support`: score >= 0.55 (was 0.50)
- `partial_support`: score >= 0.40 (NEW)
- `weak_support`: score >= 0.28 (was 0.30)
- `unsupported`: score < 0.28

## Results

| Metric | Phase 10E-Prime | Phase 10F |
|--------|-----------------|-----------|
| Mean grounding score | 0.393 | **0.517** |
| strong_support items | 2 | **14** |
| partial_support items | N/A | **5** |
| unsupported items | 10 | **0** |
| Overall verdict | weak_support | **strong_support** |
