# Pilot Campaign Results

## Benchmark Pilot

**Campaign ID**: e41724b3deee46d6
**Profile**: pilot_benchmark_validation
**Mode**: benchmark (offline-safe, FakeCandidateGenerator)
**Status**: completed_with_draft

### Results
- Champion: **Perovskite-TI Hybrid Solar Cell** (score 0.935)
- Candidates generated: 5
- Candidates shortlisted: 2
- Retries: 0
- All 5 campaign stages completed successfully

### Stage Progression
1. preflight: completed
2. lock_acquisition: completed
3. db_init: completed
4. daily_search_ladder: completed
5. artifact_export: completed

### Pipeline Verification
- DB writes: verified (campaign receipt persisted)
- Artifact generation: verified (4 files)
- Review packet creation: verified
- Policy logging: verified
- Reward logging: verified
- Failure handling: not triggered (clean run)

### Health Assessment
- Healthy: True
- Campaign succeeded: True
- Overnight ready: True
- Issues: None

## Production Pilot

**Campaign ID**: 12b92ddcd930...
**Profile**: pilot_production_validation
**Mode**: production (live Ollama)
**Status**: completed_no_draft

### Results
- Champion: none (no candidate met quality threshold)
- Candidates generated: 8
- Retries: 0
- All 5 campaign stages completed successfully

### Conclusion
Both pilots verify the autonomous pipeline works end-to-end.
The system is ready for overnight execution.
