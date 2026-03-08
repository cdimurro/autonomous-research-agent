# Domain-Fit Configuration Guide

## Overview
Domain-fit evaluation is now driven by YAML config files in `config/domain_fit/`.
No hardcoded keyword lists remain in the core logic.

## Config Structure

Each domain config file defines:

```yaml
domain: clean-energy

positive_keywords:
  - solar
  - battery
  - hydrogen
  # ... more keywords

negative_keywords:
  - crispr
  - diagnostic

weights:
  title: 0.15
  statement: 0.30
  mechanism: 0.25
  evidence: 0.15
  keyword_diversity: 0.15

min_score: 0.25
program_goal_weight: 0.30
off_domain_penalty: 0.15
```

## Available Configs

| File | Domain | Keywords |
|------|--------|----------|
| `clean_energy.yaml` | clean-energy | 37 positive, 5 negative |
| `materials.yaml` | materials | 32 positive, 5 negative |
| `cross_domain.yaml` | cross-domain | 0 (accepts all) |

## Adding a New Domain

1. Create `config/domain_fit/<domain_name>.yaml`
2. Define positive keywords (terms that indicate domain relevance)
3. Define negative keywords (off-domain terms that should penalize score)
4. Set scoring weights and thresholds
5. The evaluator will auto-discover the config via domain name matching

## Domain Name Resolution

The config loader tries these paths in order:
1. Exact match: `<domain>.yaml`
2. Hyphen-to-underscore: `<domain_with_underscores>.yaml`
3. Underscore-to-hyphen: `<domain-with-hyphens>.yaml`
4. Prefix match: first part before hyphen (e.g., `materials-science` → `materials.yaml`)

If no config is found, cross-domain behavior is used (all candidates pass).

## Scoring Formula

```
composite = title * W_title + statement * W_statement + mechanism * W_mechanism
           + evidence * W_evidence + goal_bonus + keyword_diversity * W_diversity
```

Where each relevance score is `min(1.0, matched_keywords / 3.0)`.

Off-domain penalties are subtracted per negative keyword detected.
