# Contributing

## Quick Orientation

This is a small, opinionated codebase. Before contributing, understand the core architecture:

- **Pipeline scripts** in `scripts/` run sequentially — each reads from and writes to SQLite
- **Configuration** in `config/` controls behavior — most extensions happen here, not in code
- **Evaluation** has two layers: confidence scoring (`judge-score.sh`) then rubric grading (`rubric-grade.sh`). See [`docs/EVALUATION.md`](docs/EVALUATION.md)
- **Artifact contracts** in `schemas/` define what the system produces
- **All evaluation logic is deterministic** — no LLM in the validation path

## What to Contribute

High-value contributions (in rough priority order):

- **Domain config packs** — feeds, validators, and ontologies for a specific research domain (see below)
- **Numeric validators** — add physical bounds for new metrics in `config/validators.yaml`
- **Rubric criteria** — add grading items to `config/rubrics.yaml` with deterministic logic in `scripts/rubric-grade.sh`
- **Parser improvements** — enhance PDF parsing quality in `scripts/parser-route.sh`
- **Bug fixes** — especially in edge cases around extraction, parsing, or validation
- **Feed integrations** — new RSS/API sources in `scripts/feed-ingest.sh`

## How to Contribute

1. Fork the repository
2. Create a branch: `git checkout -b feature/my-feature`
3. Make focused changes (one feature or fix per PR)
4. Run all tests:
   ```bash
   bash tests/test-schema-validation.sh
   bash tests/test-validators.sh
   bash tests/test-rubric-grading.sh
   ```
5. Run the demo to verify evaluation still works: `bash examples/demo-rubric-eval.sh`
6. Commit with a clear message and open a PR

## Guidelines

- **Prefer config over code.** If an extension can be done through YAML, don't add a script.
- **Keep evaluation deterministic.** The rubric grader and validators must not call an LLM.
- **Follow existing style.** Bash scripts use `set -euo pipefail`. Python uses standard library where possible.
- **Don't commit secrets** — API keys, personal data, or absolute paths.
- **Don't expand scope casually.** This repo is deliberately small. Read the Non-Goals section in the README before proposing large additions.

## Domain Config Packs

If you've configured the agent for a specific research domain, consider contributing a config pack under `config/examples/`:

```
config/examples/your-domain/
├── sources.yaml       # Feed definitions
├── ontologies.yaml    # Ontology mappings
├── validators.yaml    # Numeric validators
└── README.md          # Brief domain description
```

## Reporting Issues

Include: what you expected, what happened, steps to reproduce, and your environment (OS, Python version, Ollama model).
