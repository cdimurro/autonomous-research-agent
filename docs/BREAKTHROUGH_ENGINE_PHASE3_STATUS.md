# Breakthrough Engine -- Phase 3 Status

**Status: Phase 3 Complete**

## Deliverables

- [x] **A.** External retrieval from OpenAlex and Crossref APIs
- [x] **B.** Retrieval caching with configurable TTL
- [x] **C.** Novelty engine with layered heuristic evaluation
- [x] **D.** Publication draft and review workflow
- [x] **E.** Review CLI and API routes
- [x] **F.** Notification interfaces
- [x] **G.** Database migration for Phase 3 tables
- [x] **H.** Full test coverage for all new functionality

## Files Added

| File                        | Purpose                                      |
|-----------------------------|----------------------------------------------|
| `retrieval.py`              | External retrieval sources and caching        |
| `novelty.py`                | Novelty evaluation engine                     |
| `review.py`                 | Publication draft and review workflow          |
| `notifications.py`          | Notification interfaces                        |
| `test_phase3.py`            | Phase 3 test suite                             |
| 5 documentation files       | Architecture and reference docs for Phase 3    |

## Files Changed

| File               | Changes                                                  |
|--------------------|----------------------------------------------------------|
| `models.py`        | Added NoveltyResult, PriorArtHit, PublicationDraft, review event models |
| `db.py`            | Added table definitions and queries for Phase 3 tables    |
| `orchestrator.py`  | Integrated novelty gate, review workflow, retrieval       |
| `api.py`           | Added review queue and draft API routes                   |
| `cli.py`           | Added review subcommands (list, show, approve, reject)    |

## Migration

**v002** adds five tables:

| Table                  | Purpose                                    |
|------------------------|--------------------------------------------|
| `bt_novelty_checks`   | Persisted novelty evaluation results        |
| `bt_publication_drafts`| Drafts awaiting review                      |
| `bt_review_events`    | Audit trail of review actions               |
| `bt_run_metrics`      | Per-run performance and pipeline metrics    |
| `bt_retrieval_cache`  | Cached external retrieval results           |

## Test Status

**176 passed, 0 failed**

- 124 tests from Phase 1 and Phase 2 preserved and passing
- 52 new tests added in Phase 3

## Known Limitations

- **Live retrieval:** OpenAlex and Crossref require live internet access for real data. All tests use mocked HTTP responses.
- **Lexical novelty:** The novelty engine uses heuristic lexical analysis, not embedding-based semantic similarity. This catches obvious overlaps but may miss paraphrased duplicates.
- **Webhook notifier:** The webhook notification channel is interface-only; a concrete implementation requires deployment-specific configuration.
- **Review UI:** No HTML views for the review queue yet. Review is available via CLI and JSON API only.

## Next Steps

1. Stand up live retrieval against OpenAlex and Crossref with API keys and rate limit configuration.
2. Run the system in `production_review` mode with real review cycles.
3. Implement embedding-based novelty evaluation to complement the current lexical heuristics.
4. Build an HTML review dashboard for the review queue and draft inspection.
