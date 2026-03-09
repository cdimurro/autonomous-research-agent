# Production Embeddings Configuration

## Phase 7B Status

**Production embedding provider**: `OllamaEmbeddingProvider`
**Model**: `nomic-embed-text:latest`
**Host**: `127.0.0.1:11434` (local Ollama)
**Dimension**: 768
**Status**: Active for Phase 7B overnight campaigns

## How It Works

### Configuration

Set the `BT_EMBEDDING_MODEL` environment variable before launching:

```bash
export BT_EMBEDDING_MODEL=nomic-embed-text
```

When this is set:
1. `BreakthroughOrchestrator` uses `OllamaEmbeddingProvider(model=nomic-embed-text)`
2. Preflight checks that the model is available and reports FAIL if not
3. Campaign receipt records `OllamaEmbeddingProvider(nomic-embed-text)`

When unset:
1. `BreakthroughOrchestrator` uses `MockEmbeddingProvider` (deterministic hash-based)
2. Preflight PASS with note: "MockEmbeddingProvider — set BT_EMBEDDING_MODEL for real embeddings"
3. Campaign receipt records `MockEmbeddingProvider`

### Code Path

```
BreakthroughOrchestrator.__init__
  → os.environ.get("BT_EMBEDDING_MODEL", "")
  → if set and production mode:
      OllamaEmbeddingProvider(model=embed_model)
  → else:
      MockEmbeddingProvider()  (+ warning if production mode)
  → EmbeddingNoveltyEngine(provider=emb_provider)
```

### Preflight Check Behavior

| Condition | Status | Message |
|-----------|--------|---------|
| BT_EMBEDDING_MODEL not set | PASS | "Using MockEmbeddingProvider (BT_EMBEDDING_MODEL not set)" |
| BT_EMBEDDING_MODEL set, model available | PASS | "OllamaEmbeddingProvider(X) available — real embeddings active" |
| BT_EMBEDDING_MODEL set, Ollama unreachable | FAIL | "BT_EMBEDDING_MODEL=X is set but Ollama is unreachable" |
| BT_EMBEDDING_MODEL set, model not found | FAIL | "BT_EMBEDDING_MODEL=X is set but model not found in Ollama" |

FAIL on embedding check blocks strict preflight → blocks campaign launch.

## What Embeddings Do

The `EmbeddingNoveltyEngine` adds a semantic layer on top of lexical novelty checking:

1. Embeds the candidate (title + statement + mechanism)
2. Embeds prior candidates and retrieved evidence
3. Computes cosine similarities
4. Flags semantic near-duplicates that lexical methods miss
5. Returns `EmbeddingNoveltyDetail` with `novelty_basis`, `nearest_neighbors`, `blocked_by_prior_art`

### Thresholds
- `similarity_threshold = 0.88` → block (prior-art hit)
- `warn_threshold = 0.78` → flag as near-neighbor

### Mock vs Real

| | MockEmbeddingProvider | OllamaEmbeddingProvider |
|---|---|---|
| Embedding type | Deterministic MD5 hash | nomic-embed-text (768d) |
| Offline-safe | Yes | Requires Ollama running |
| Similarity structure | Word-overlap approximation | Semantic similarity |
| Use case | Tests, CI, offline | Production campaigns |

## Campaign History

| Campaign | Embedding Provider | Notes |
|----------|--------------------|-------|
| b87513b86b6f4b1f | MockEmbeddingProvider | Phase 7A overnight run |
| b80c979d75144fb8 | OllamaEmbeddingProvider(nomic-embed-text) | Phase 7B smoke |
| f01a0a7c72304481 | OllamaEmbeddingProvider(nomic-embed-text) | Phase 7B overnight |

## Launch Command (with real embeddings)

```bash
env PYTHONUNBUFFERED=1 BT_EMBEDDING_MODEL=nomic-embed-text \
  nohup /Users/openclaw/breakthrough-engine/.venv/bin/python \
  -m breakthrough_engine campaign run --profile overnight_clean_energy \
  > nohup_campaign.log 2>&1 &
```

## Verifying Embeddings Were Used

```bash
# Check campaign receipt
.venv/bin/python -c "
import json, sqlite3
conn = sqlite3.connect('runtime/db/scires.db')
row = conn.execute(
  'SELECT embedding_provider, status FROM bt_campaign_receipts WHERE campaign_id=?',
  ('<CAMPAIGN_ID>',)
).fetchone()
print('Embedding provider:', row[0])
print('Status:', row[1])
"

# Or check evaluation pack
cat runtime/evaluation_packs/<CAMPAIGN_ID>/evaluation_pack.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('Embedding provider:', d['models']['embedding_provider'])
print('Embedding model:', d['models']['embedding_model'])
"
```
