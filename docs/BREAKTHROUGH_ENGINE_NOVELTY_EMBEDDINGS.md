# Breakthrough Engine - Embedding-Based Novelty (Phase 4B)

## Overview

Phase 4B adds an embedding-based semantic novelty layer on top of the existing lexical novelty engine. This catches conceptually similar hypotheses that lexical heuristics miss.

## Architecture

```
NoveltyEngine (lexical, Phase 3)
  |
  +-- EmbeddingNoveltyEngine (semantic, Phase 4B)
  |     |-- EmbeddingProvider (ABC)
  |     |     |-- MockEmbeddingProvider (tests)
  |     |     |-- OllamaEmbeddingProvider (local-first)
  |     |
  |     +-- cosine_similarity()
  |
  +-- Combined decision in orchestrator
```

## Layered Novelty Decision

The combined novelty check uses:

1. **Exact title match** (lexical) — threshold 0.95 → FAIL
2. **Statement overlap** (lexical) — threshold 0.80 → FAIL
3. **Mechanism overlap** (lexical) — threshold 0.75 → FAIL
4. **Keyword overlap** (lexical) — threshold 0.60 → WARN
5. **Embedding similarity** (semantic) — threshold 0.88 → BLOCK
6. **Embedding warning** (semantic) — threshold 0.78 → noted in neighbors

A candidate is blocked if **either** the lexical engine hard-fails or the embedding engine detects a near-duplicate.

## Embedding Provider

### Primary: `nomic-embed-text` via Ollama
- 768-dimensional embeddings
- Runs locally, no API keys
- Good quality for scientific text similarity
- Environment variable: `BT_EMBEDDING_MODEL`

### Fallback: `MockEmbeddingProvider`
- 64-dimensional hash-based embeddings
- Deterministic and reproducible
- Preserves word-level similarity structure
- Used in all tests

### Provider Abstraction
`EmbeddingProvider` ABC with `embed(texts)` and `dimension()` methods.

## Persisted Output

`EmbeddingNoveltyDetail` includes:
- `embedding_similarity_max`: highest cosine similarity found
- `nearest_neighbors`: top 5 similar items with titles and scores
- `novelty_basis`: "lexical_only", "embedding_assisted", or "embedding_primary"
- `blocked_by_prior_art`: boolean flag

Stored in `bt_embedding_novelty` table (v003 migration).

## Threshold Calibration

| Threshold | Value | Rationale |
|-----------|-------|-----------|
| Embedding block | 0.88 | High confidence semantic duplicate |
| Embedding warn | 0.78 | Moderate similarity, flagged for review |
| Lexical exact title | 0.95 | Near-identical titles |
| Lexical statement | 0.80 | High statement overlap |
| Lexical mechanism | 0.75 | High mechanism overlap |

These thresholds are configurable via `NoveltyEngine` and `EmbeddingNoveltyEngine` constructor parameters.

## Testing

Tests in `test_phase4b.py::TestEmbeddingNovelty`:
- Mock embeddings are deterministic
- Similar texts have higher similarity than dissimilar texts
- No prior art returns clean result
- Self-similarity detects duplicates
- Different topics are not blocked
- Cosine similarity edge cases (identical, orthogonal, empty)

Golden calibration cases:
- Semantic duplicate detection
- Different-domain candidate allowed
