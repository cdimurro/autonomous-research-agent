# Phase 10G: Rollback and Safety Guardrails

**Date:** 2026-03-13
**Branch:** `breakthrough-engine-phase10g-retrieval-ab`

## Production Safety

1. **Live production retrieval is UNCHANGED.** The default `LadderConfig` uses
   `ExistingFindingsSource` with flat generation. No code in this phase changes
   that default.

2. **Graph-native retrieval is opt-in only.** It activates exclusively when
   `evidence_source_override` and `enable_graph_context=True` are explicitly
   set in `LadderConfig`. This is only done in the experiment script.

3. **No merge to main.** All work stays on the experiment branch.

## Experiment Abort Conditions

The A/B experiment should be aborted if any of the following occur:

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Graph-native mean score regression | > 0.05 below current arm | ABORT experiment |
| Graph-native approval rate | < 40% | ABORT experiment |
| Systematic runtime failures | > 50% campaigns fail | ABORT experiment |
| Integrity/falsification regression | Any new falsification failures | ABORT experiment |
| Novel crash modes | Any crash not seen in Phase 10F | ABORT experiment |

## Control Arm Launch Command

```bash
source .env
.venv/bin/python scripts/phase10g_retrieval_ab.py
```

Both arms are launched from the same script. The control arm uses default
`LadderConfig(mode="benchmark")`. The graph arm uses:
```python
LadderConfig(
    mode="benchmark",
    evidence_source_override=hybrid_source,
    enable_graph_context=True,
)
```

## Rollback Path (If Graph-Native Were Later Promoted)

To revert graph-native retrieval after a hypothetical future promotion:

1. Remove `evidence_source_override` from the production `LadderConfig`
2. Remove `enable_graph_context=True` from the production `LadderConfig`
3. The pipeline immediately reverts to `ExistingFindingsSource` + flat template
4. No database migration needed
5. No embedding change needed

This is a config-only reversion — no code changes required.

## Current Retrieval Recovery

The current retrieval path (`ExistingFindingsSource` + flat generation) is
always available as the default. It cannot be accidentally disabled because:

- `LadderConfig.evidence_source_override` defaults to `None`
- `LadderConfig.enable_graph_context` defaults to `False`
- `BreakthroughOrchestrator` defaults to `ExistingFindingsSource`
- Tests verify these defaults (test_phase10f.py, test_phase10a.py)
