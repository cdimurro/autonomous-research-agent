# Phase 4C Plan: Operational Hardening

## Objective
Make the Breakthrough Engine operationally stronger and more trustworthy in real use. No new architecture — focus on production validation, workflow completion, configurability, and observability.

## Priorities

### Priority 1: Review UI Action Completion
- Wire approve/reject to backend via HTML form submission
- Add confirmation dialogs and reviewer/reason fields
- Support both JSON API and HTML form workflows
- Preserve one-publication-per-run invariant

### Priority 2: Domain-Fit Config Externalization
- Move hardcoded keyword lists to `config/domain_fit/*.yaml`
- Support per-domain config: positive keywords, negative keywords, weights, thresholds
- Add config loading with caching and fallback

### Priority 3: Embedding Observability & Drift Monitoring
- Per-run embedding stats: model, dim, thresholds, block/warn counts, similarity distribution
- Cross-run drift analysis: similarity trends, saturation detection, repeated neighbors
- Persist via new `bt_embedding_monitor` table

### Priority 4: Threshold Calibration Diagnostics
- Per-run calibration diagnostics: blocks, domain-fit fails, publication pass/fail reasons
- Active thresholds endpoint for visibility
- Persist via new `bt_calibration_diagnostics` table

### Priority 5: Live Embedding Validation
- Run real Ollama embeddings (nomic-embed-text) in production_shadow and production_review
- Record and compare behavior against Phase 4A/4B baseline

## Constraints
- No architecture redesign
- No full dashboard or SPA
- No live Omniverse execution
- All tests offline-safe
- Preserve one-publication-per-run invariant
