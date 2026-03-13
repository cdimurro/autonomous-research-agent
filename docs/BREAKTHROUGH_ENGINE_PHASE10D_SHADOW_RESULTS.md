# Phase 10D Shadow Results

## Retrieval-Level 3-Way Comparison

| Metric | Current | KG (pure) | Hybrid |
|--------|---------|-----------|--------|
| Mean relevance | 0.8793 | 0.4888 | 0.8725 |
| Unique sources | 11 | 8 | 11 |
| Source types | 1 (finding) | 1 (kg_segment) | 2 (finding + kg_segment) |
| Items | 30 | 30 | 30 |

### Key Observations

1. **Pure KG still uncompetitive** (mean 0.49 uncalibrated) — confirms Phase 10C finding
2. **Hybrid preserves score quality** (0.8725, delta -0.0068 from current)
3. **Hybrid adds source-type diversity** (2 types vs 1)
4. **Hybrid reduces monoculture** (top-1 concentration 13.3%)
5. **Calibration works** — KG items calibrated from ~0.58 to ~0.82 range

### Hybrid Evidence Mix

- 20 trusted finding items (66.7%)
- 10 KG segment items (33.3%)
- 8 KG items deduplicated (overlapping source_ids removed)

## Campaign-Level Comparison

**DEFERRED** — Requires live Ollama for candidate generation. Retrieval-level evidence supports proceeding to campaign trial when infrastructure is available.

## Verdict

Hybrid retrieval is the correct path forward. Pure KG replacement remains non-viable even with calibration, but hybrid composition successfully preserves trusted signals while adding diversity.
