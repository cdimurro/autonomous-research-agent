# Breakthrough Engine - Benchmarks

## Running Benchmarks

```bash
python -m breakthrough_engine benchmark run
```

## Golden Cases

The benchmark suite includes 9 regression tests covering:

| Case | What It Tests |
|------|---------------|
| `full_cycle_publication` | Standard cycle with good candidates produces a publication |
| `one_pub_per_run` | At most one publication per run (invariant) |
| `generic_rejected` | Generic/unusable candidate is rejected by hypothesis harness |
| `evidence_poor_rejected` | Candidate with insufficient evidence is rejected |
| `overconfident_warning` | Overconfident claims trigger warnings or failures |
| `score_ranges` | All score dimensions stay within [0.0, 1.0] |
| `rejection_reasons` | All rejected candidates have recorded reasons |
| `high_threshold_no_pub` | Very high publication threshold produces no publication |
| `deterministic` | Two identical runs produce identical results |

## Golden Fixture Candidates

Available in `breakthrough_engine/benchmark.py`:

- `golden_high_quality()` — publishable, well-evidenced candidate
- `golden_generic()` — empty/vague candidate (should fail hypothesis harness)
- `golden_duplicate(prior)` — near-duplicate of a prior candidate
- `golden_evidence_poor()` — candidate with no evidence attachments
- `golden_overconfident()` — candidate making "confirmed discovery" claims
- `golden_simulation_unready()` — candidate with 1-year testability window
- `golden_publishable_finalist()` — strong but not top-pick candidate

## Custom Benchmarks

Use `BenchmarkCandidateGenerator` to create benchmarks with specific candidates:

```python
from breakthrough_engine.benchmark import BenchmarkCandidateGenerator, golden_high_quality

gen = BenchmarkCandidateGenerator([golden_high_quality()])
# Use with orchestrator for custom regression tests
```

## Output Format

```
Benchmark Suite: 9/9 passed, 0 failed (8ms)

  [PASS] full_cycle_publication (2ms)
  [PASS] one_pub_per_run (1ms)
  ...
```
