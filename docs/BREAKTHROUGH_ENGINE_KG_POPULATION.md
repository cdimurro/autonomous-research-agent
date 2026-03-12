# KG Population — Phase 10B

## Population Method

1. **Findings ingestion**: 18 papers from `findings` table (accepted, clean-energy relevant)
2. **Evidence items ingestion**: 378 items from `bt_evidence_items` (all prior campaign evidence)
3. **Embedding scoring**: All segments scored using qwen3-embedding:4b (2560d) against domain anchor
4. **Entity/relation extraction**: Real LLM extraction via qwen3.5:9b-q4_K_M

## Population Stats

| Metric | Value |
|--------|-------|
| Total segments | 396 |
| From findings | 18 papers |
| From evidence items | 378 items |
| Scored segments | 369+ |
| Extracted segments | 27 |
| Entities | 168 |
| Relations | 94 |
| Extraction errors | 0 (after bug fix) |

## Entity Type Distribution

| Type | Count |
|------|-------|
| metric | 39+ |
| device | 29+ |
| compound | 21+ |
| property | 15+ |
| process | 11+ |
| method | 10+ |
| material | 7+ |
| structure | 5+ |
| phenomenon | 4+ |
| mechanism | 4+ |
| concept | 1+ |

## Relation Type Distribution

| Type | Count |
|------|-------|
| measured_by | 29+ |
| related_to | 27+ |
| composed_of | 9+ |
| used_in | 6+ |
| enables | 4+ |
| produces | 3+ |
| enhances | 2+ |
| causes | 2+ |
| requires | 1+ |

## Quality Notes

- 0 empty entity names
- 8 short entity names (<3 chars — mostly numeric metrics like "2.19 V")
- 49 duplicate canonical names (expected: same concepts appear across papers)
- Extraction quality is good — entities are scientifically meaningful
- Top duplicates: "all-perovskite tandem solar cells" (5x), "33.7% efficiency" (5x)

## Extraction Ongoing

27 of 396 segments extracted at time of comparison. Extraction can be resumed:

```bash
source .env
PYTHONPATH=. .venv/bin/python -c "
from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.kg_extractor import EntityRelationExtractor, ExtractionConfig
db = init_db('runtime/db/scires.db')
repo = Repository(db)
extractor = EntityRelationExtractor(repo, config=ExtractionConfig(), mock=False)
stats = extractor.extract_from_segments(domain='clean-energy', limit=400)
print(stats)
"
```
