# Breakthrough Engine - Model Strategy

## Status: Initial Strategy Defined (Phase 4A)

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
| JSON compliance | Good (with /no_think prefix) | Good |
| Speed (M-series) | ~15-30 tok/s | ~20-40 tok/s |
| VRAM | ~6GB Q4 | ~5GB Q4 |
| Context | 32K | 128K |
| Availability | Ollama registry | Ollama registry |

## What Remains Deferred

1. **Multi-model orchestration**: Not needed. Single model for generation is sufficient.
2. **API-based models (Claude, GPT)**: Not needed for local-first operation. Can be added later if quality demands it.
3. **Embedding models**: Not needed until embedding-based novelty (Phase 4B).
4. **Fine-tuned models**: Premature. Need real run data first to know what to fine-tune on.

## Upgrade Path

If Phase 4A shadow runs show poor generation quality:
1. First: tune the prompt (cheapest fix)
2. Second: try backup model
3. Third: try larger model (e.g., `qwen3.5:32b-q4_K_M`)
4. Last resort: add API-based model (Claude API)
