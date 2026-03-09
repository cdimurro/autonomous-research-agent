# Phase 7B Plan: Production Hardening, Evaluation Pack Capture, Overnight Relaunch

**Branch**: `breakthrough-engine-phase7b-prod-hardening`
**Base**: `breakthrough-engine-phase7a-autonomous-ops` @ commit `b5638d2` (then `f70507f`)
**Started**: 2026-03-09
**Status**: IN PROGRESS

## Baseline State

| Attribute | Value |
|-----------|-------|
| Branch | breakthrough-engine-phase7b-prod-hardening |
| Base commit | f70507f (overnight profile fix on top of b5638d2) |
| Schema version | v008 |
| Tests passing | 506 |
| Generation model | qwen3.5:9b-q4_K_M |
| Embedding model (production) | **MockEmbeddingProvider** — TRUST GAP |
| Embedding model (available) | nomic-embed-text:latest via Ollama |
| Overnight campaign (Phase 7A) | b87513b86b6f4b1f — completed_with_draft |
| Champion | Hybrid Offshore TPV-Wind Systems for Nighttime Grid Stabilization (0.947) |
| Overnight launch command | `env PYTHONUNBUFFERED=1 nohup /Users/openclaw/breakthrough-engine/.venv/bin/python -m breakthrough_engine campaign run --profile overnight_clean_energy > nohup_campaign.log 2>&1 &` |

## Verified Trust Gaps

1. **Mock embeddings in production**: `BreakthroughOrchestrator` defaults to `MockEmbeddingProvider()` regardless of mode. `nomic-embed-text:latest` is available in Ollama but unused.
2. **Embedding preflight is ADVISORY**: `embedding_model` check returns WARN (not FAIL) even in strict mode.
3. **No evaluation pack**: Phase 7A campaign artifacts lack full finalist traces, score breakdowns, tie-break rationale, and external-analysis-ready structured output.
4. **No embedding telemetry**: Campaign receipts and artifacts don't record which embedding provider was used.
5. **Overnight profile had wrong program**: `daily_quality` → fixed to `clean_energy_shadow` (committed).

## Implementation Order

| Priority | Deliverable | Status |
|----------|-------------|--------|
| P1 | Evaluation pack exporter (evaluation_pack.py) | pending |
| P1 | Export pack for b87513b86b6f4b1f | pending |
| P1 | Production embedding hardening | pending |
| P2 | Schema v009 (bt_evaluation_packs, embedding_provider column) | pending |
| P2 | Preflight: FAIL in strict mode if embedding model missing | pending |
| P2 | Campaign receipt: record embedding provider | pending |
| P3 | Smoke campaign profile (smoke_10m.yaml) | pending |
| P3 | CLI: evaluation-pack commands | pending |
| P4 | Tests (test_phase7b.py) | pending |
| P4 | Full test suite run | pending |
| P5 | Strict preflight + smoke campaign | pending |
| P5 | Second overnight campaign launch | pending |

## Key Design Decisions

- `BT_EMBEDDING_MODEL` env var gates real vs mock embedding: if set, use `OllamaEmbeddingProvider`; if unset, use `MockEmbeddingProvider`
- In strict preflight: `embedding_model` check is FAIL if `BT_EMBEDDING_MODEL` is set but model unavailable
- In strict preflight: `embedding_model` check is WARN if `BT_EMBEDDING_MODEL` is unset (mock mode) — this is acceptable for tests
- For the second overnight campaign: set `BT_EMBEDDING_MODEL=nomic-embed-text` in the launch env
- `EvaluationPackExporter` queries DB directly for full candidate/score/falsification/posterior data
- Evaluation packs stored at `runtime/evaluation_packs/<campaign_id>/`
- Schema v009 adds `bt_evaluation_packs` (tracking table) and `embedding_provider` to `bt_campaign_receipts`
