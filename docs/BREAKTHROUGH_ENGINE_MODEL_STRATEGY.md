# Breakthrough Engine - Model Strategy

## Status: Updated for Phase 4C (live embedding validation)

## Decision Context

The Breakthrough Engine needs AI models for:
1. **Candidate hypothesis generation** (primary, needed now)
2. **Critique/review** (future, not needed for Phase 4A)
3. **Evidence extraction/cleanup** (future, handled by upstream pipeline)

This document defines the initial model selections for Phase 4A live runs.

## Model Decision Table

| Role | Primary Model | Backup Model | Why Selected | Cost | Required Now? |
|------|--------------|--------------|--------------|------|---------------|
| Candidate generation | `qwen3.5:9b-q4_K_M` (Ollama) | `llama3.1:8b` (Ollama) | Already configured in `config/models.yaml`, good reasoning quality at 9B, runs well on Apple Silicon | $0 (local) | **Yes** |
| Evidence extraction | `qwen3.5:9b-q4_K_M` (Ollama) | N/A | Handled by upstream pipeline, not breakthrough engine | $0 | No |
| Critique/review | Deferred | Deferred | No automated critique in Phase 4A; human review only | N/A | No |
| Novelty assessment | Rule-based (no LLM) | N/A | Current lexical novelty engine works without LLM | $0 | Yes (already working) |
| Scoring | Rule-based (no LLM) | N/A | Deterministic formula, no LLM needed | $0 | Yes (already working) |

## Primary Model: Qwen 3.5 9B (Q4_K_M)

### Why this model?

1. **Already configured**: `config/models.yaml` specifies this as the primary model
2. **Local-first**: Runs via Ollama, no API keys or cloud costs
3. **Apple Silicon optimized**: Good performance on M-series Macs
4. **32K context window**: Sufficient for evidence block + generation prompt
5. **Structured output capable**: Can produce JSON arrays reliably with proper prompting
6. **Cost**: $0/token (local inference)

### Configuration

```yaml
# Already in config/models.yaml
model_id: "qwen3.5:9b-q4_K_M"
context_window: 32768
max_output_tokens: 8192
```

```python
# Already in candidate_generator.py OllamaConfig
model: str = "qwen3.5:9b-q4_K_M"
temperature: float = 0.7
max_tokens: int = 4096
timeout_seconds: int = 300
```

### Environment overrides

```bash
export OLLAMA_MODEL="qwen3.5:9b-q4_K_M"     # Change model
export OLLAMA_HOST="127.0.0.1:11434"          # Change host
export BT_OLLAMA_TEMPERATURE="0.7"            # Change temperature
export BT_OLLAMA_MAX_TOKENS="4096"            # Change max tokens
export BT_OLLAMA_TIMEOUT="300"                # Change timeout
```

## Backup Model: Llama 3.1 8B

If Qwen 3.5 9B is unavailable or produces poor quality:

```bash
export OLLAMA_MODEL="llama3.1:8b"
```

Llama 3.1 8B is widely available, well-tested, and has good JSON output compliance. Lower reasoning quality than Qwen 3.5 but adequate as a fallback.

## Performance/Reliability Tradeoffs

| Dimension | Qwen 3.5 9B | Llama 3.1 8B |
|-----------|-------------|--------------|
| Generation quality | Good | Adequate |
| JSON compliance | Good (with `think: false` API flag) | Good |
| Speed (M-series) | ~15-30 tok/s | ~20-40 tok/s |
| VRAM | ~6GB Q4 | ~5GB Q4 |
| Context | 32K | 128K |
| Availability | Ollama registry | Ollama registry |

## Phase 4B: Embedding Model Strategy

### Embedding Decision Table

| Role | Primary Model | Backup | Why Selected | Cost | Required Now? |
|------|--------------|--------|--------------|------|---------------|
| Novelty embeddings | `qwen3-embedding:4b` (Ollama) | `MockEmbeddingProvider` | 2560d, top MTEB quality, local-first | $0 (local) | Optional (mock fallback works) |

### Primary: qwen3-embedding:4b

- **2560-dimensional** embeddings
- **Local-first**: Runs via Ollama, no API keys
- **Top MTEB quality** for scientific text similarity tasks (outperforms nomic-embed-text by ~6 points avg)
- **Environment override**: `BT_EMBEDDING_MODEL=qwen3-embedding:4b`
- **Fallback**: If Ollama embedding endpoint is unavailable, the system falls back to `MockEmbeddingProvider` (deterministic hash-based, always available)

### Separation of Concerns

| Component | Model | Purpose |
|-----------|-------|---------|
| Candidate generation | qwen3.5:9b-q4_K_M | Generate hypotheses from evidence |
| Novelty embeddings | qwen3-embedding:4b | Detect semantic near-duplicates |
| Scoring | Rule-based (no LLM) | Deterministic formula |
| Domain-fit | Rule-based (no LLM) | Keyword-based relevance |

The embedding model is used **only** for novelty detection. It does not influence candidate generation, scoring, or publication decisions directly.

### Thinking-Mode Disable Mechanism

The Ollama API payload uses `"think": False` (Python bool) in the JSON body to disable thinking mode for Qwen 3.5. This was changed from the original `/no_think` prefix approach in Phase 4A after observing that the model spent all tokens on thinking when thinking mode was enabled.

## Phase 4C: Production Embedding Validation

### Actual runtime configuration (verified):
- **Generation model**: `qwen3.5:9b-q4_K_M` via Ollama (confirmed running)
- **Embedding model**: `nomic-embed-text` via Ollama (768d, pulled and verified)
- **Thinking mode**: `"think": False` in API payload (no `/no_think` prefix)
- **Mock fallback**: `MockEmbeddingProvider` (64d hash-based, always available)

### Domain-fit model: Rule-based (no LLM)
- Keyword matching from YAML config files (`config/domain_fit/`)
- No LLM involvement in domain-fit evaluation
- Configurable per domain without code changes

### Embedding monitoring
- Per-run embedding stats persisted in `bt_embedding_monitor`
- Cross-run drift analysis via `EmbeddingMonitor.get_drift_report()`
- Saturation detection and repeated-neighbor clustering

## What Remains Deferred

1. **Multi-model orchestration**: Not needed. Single model for generation is sufficient.
2. **API-based models (Claude, GPT)**: Not needed for local-first operation. Can be added later if quality demands it.
3. **Fine-tuned models**: Premature. Need real run data first to know what to fine-tune on.
4. **LLM-based critique/review**: Deferred. Human review is the current quality gate.
5. **LLM-based domain classification**: Deferred. Keyword-based approach is working and now configurable.

## Upgrade Path

If Phase 4A shadow runs show poor generation quality:
1. First: tune the prompt (cheapest fix)
2. Second: try backup model
3. Third: try larger model (e.g., `qwen3.5:32b-q4_K_M`)
4. Last resort: add API-based model (Claude API)
