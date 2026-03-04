# Contributing

Thanks for your interest in contributing to the Autonomous Research Agent!

## How to Contribute

1. **Fork** the repository
2. **Create a branch** for your feature or fix: `git checkout -b feature/my-feature`
3. **Make your changes** and test them
4. **Commit** with a clear message describing what and why
5. **Push** and open a Pull Request

## What to Contribute

- **New feed sources**: Add RSS/API integrations in `scripts/feed-ingest.sh`
- **Domain validators**: Add numeric range validators in `config/validators.yaml`
- **Ontology mappings**: Add domain ontologies in `config/ontologies.yaml`
- **Parser improvements**: Enhance PDF parsing in `scripts/parser-route.sh`
- **Bug fixes**: Fix issues and improve reliability
- **Documentation**: Improve README, add examples, write guides
- **Domain configs**: Share complete config bundles for specific research domains (e.g., medicine, climate science, materials)

## Guidelines

- Keep changes focused — one feature or fix per PR
- Test your changes: run `bash tests/test-schema-validation.sh` and `bash tests/test-validators.sh`
- Don't commit secrets, API keys, or personal data
- Follow existing code style (bash scripts use `set -euo pipefail`, Python uses standard library where possible)

## Reporting Issues

Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your environment (OS, Python version, Ollama model)

## Domain Config Packs

If you've configured the agent for a specific research domain and want to share it, consider contributing a "domain pack" — a folder under `config/examples/` containing:
- `sources.yaml` — feed definitions for that domain
- `ontologies.yaml` — relevant ontology mappings
- `validators.yaml` — domain-specific numeric validators
- A brief README explaining the domain and how to use the config
