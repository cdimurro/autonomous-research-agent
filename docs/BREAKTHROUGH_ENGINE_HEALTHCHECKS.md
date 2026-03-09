# Health Checks Reference

## Preflight Checks (15 total)

### Critical (FAIL blocks campaign in strict mode)

| Check | What it validates | Remediation |
|-------|-------------------|-------------|
| python_environment | Key packages importable | `pip install <package>` |
| db_reachable | DB file exists and readable | Check permissions |
| ollama_server | Ollama HTTP endpoint reachable | `ollama serve` |
| generation_model | Target model available | `ollama pull <model>` |
| write_access | Runtime directories writable | Fix permissions |
| config_files | Required config files present | Restore from repo |
| review_pipeline | Review/falsification modules loadable | Check installation |
| campaign_lock | No active lock file | Remove stale lock |

### Advisory (WARN does not block)

| Check | What it validates | Remediation |
|-------|-------------------|-------------|
| schema_version | At latest migration | Run `init_db()` |
| pending_migrations | No unapplied migrations | Run `init_db()` |
| embedding_model | Embedding model available | `ollama pull <model>` |
| disk_space | 5GB+ free | Free disk space |
| research_programs | Programs loadable | Check config dir |
| clean_energy_findings | Findings above threshold | Run bootstrap |
| campaign_profiles | Profile configs exist | Create profiles |

## Post-Campaign Health Assessment

| Metric | Default Threshold | Effect |
|--------|-------------------|--------|
| min_candidates_generated | pilot: 3, overnight: 10 | healthy=False if below |
| min_stages_completed | pilot: 3, overnight: 4 | healthy=False if below |
| max_stage_failure_rate | pilot: 50%, overnight: 30% | healthy=False if above |
| max_retry_count | pilot: 3, overnight: 10 | healthy=False if above |

## Overnight Readiness Gate

`overnight_ready` = True when:
- All health metrics pass
- Campaign completed (not aborted)
- Retries used <= 1

## Readiness Score

Score = sum(weights) / count(checks)
- PASS = 1.0
- WARN = 0.5
- FAIL = 0.0

Campaign is READY when:
- No FAIL checks
- Readiness score >= 0.7
