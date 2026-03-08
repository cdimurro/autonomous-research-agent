# GSD - Blockers

## Active

None. All Phase 4A and 4B blockers resolved.

## Resolved

### B1: All breakthrough files untracked
- **Resolution:** Committed as d5408ad, tagged breakthrough-engine-phase3-calibrated
- **Date:** 2026-03-07

### B2: Ollama not running
- **Resolution:** Started with `ollama serve`; qwen3.5:9b-q4_K_M model already pulled
- **Date:** 2026-03-08

### B3: No real findings in scires.db
- **Resolution:** Bootstrapped 12 papers, 18 findings via bootstrap_findings.py
- **Date:** 2026-03-08

### B4: Ollama thinking-mode timeout
- **Resolution:** Added `think: false` to API payload in candidate_generator.py
- **Date:** 2026-03-08
