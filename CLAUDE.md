# CLAUDE.md

## Mission

Breakthrough Engine is an **energy foundation system** designed to accelerate the pace of energy innovation through:

- simulation
- validation
- optimization loops
- machine learning compounding over time

The goal is **not** to be a generic research chatbot or a vague autonomous scientist.

The goal is to build a system that can take a well-defined energy problem, turn it into a **repeatable optimization loop with measurable outcomes**, run fixed experiments, score candidates conservatively, learn from every result, and improve over time.

This repository should evolve toward a system that is:

- scientifically legible
- operationally disciplined
- benchmark-driven
- commercially useful
- difficult to replicate because it compounds private data, receipts, memory, and solver-backed validation

---

## North Star

Build the **first commercially useful energy foundation system**.

In practical terms, that means:

1. The system can operate across multiple energy domains.
2. Each domain is implemented as a **benchmark-grade optimization loop**.
3. Each loop has:
   - fixed experiment templates
   - explicit scorecards
   - hard fail gates
   - selective promotion
   - memory-guided search
   - structured artifacts
4. The system learns from:
   - successful candidates
   - rejected candidates
   - hard-fail cases
   - stress/robustness behavior
   - benchmark results
5. Over time, this produces a compounding private corpus that can support a true shared energy prior or future energy foundation model.

---

## What This Project Is

Breakthrough Engine is:

- a **scientific optimization loop engine**
- a **benchmark foundry for energy domains**
- a **candidate generation and validation system**
- a **memory-building system for technical search**
- a **platform for turning scientific questions into measurable optimization loops**

Breakthrough Engine is **not** currently:

- a general AGI scientist
- a paper generator first
- a broad multi-domain playground
- an Omniverse-first platform
- a generic chat UI
- a giant monolithic physics model

---

## Core Product Thesis

The most valuable thing we can build is **not** one giant model that "knows all physics."

The winning path is:

1. Build **high-quality benchmark loops** in narrow energy domains.
2. Add **solver-backed validation** where it materially improves trust.
3. Store **every result, failure, and caveat** as structured memory.
4. Reuse those receipts and memories to improve future search.
5. Later, train a **shared latent energy prior** across domains.

This means the architecture should favor:

- benchmark loops first
- specialist domain packs
- conservative decision logic
- deterministic artifacts
- solver sidecars where needed
- active learning and memory
- delayed unification of learned priors

---

## Current Strategic Direction

The current direction of the repository is:

1. Maintain a stable broad engine core (orchestrator, campaign system, policy framework, KG retrieval).
2. Treat benchmark domains as the main proving grounds.
3. Keep domain expansion disciplined.
4. Deepen the highest-value energy domains before adding breadth.
5. Defer higher-fidelity simulation layers until they change real decisions.

### Current benchmark domains

| Domain | Module | Status |
|--------|--------|--------|
| PV I-V Characterization (`pv_iv`) | `pv_domain.py`, `pv_loop.py` | Complete — pvlib single-diode, 5 metrics, 4 templates, 6 families |
| Battery ECM + Cycle (`battery_ecm`) | `battery_domain.py`, `battery_loop.py` | Complete (v2) — Thevenin 1RC, 9 metrics, 8 templates, 7 families, fast-charge and degradation-aware |

### Planned domain order
1. PV (complete)
2. Battery (complete, v2 deepened)
3. DC-DC converter efficiency mapping

### Deferred
- cathode chemistry invention
- atomistic discovery
- Omniverse escalation
- broad UI / app work
- generic multi-domain expansion
- unnecessary architecture sprawl

---

## Architecture Doctrine

When implementing code, always prefer this mental model:

### Layer 1: Benchmark loops
Each domain should be a repeatable optimization loop with:
- bounded candidate generation
- fixed experiment templates
- fixed metrics
- explicit score weights
- hard fail gates
- promotion / rejection / alternate decisions
- benchmark artifact output

### Layer 2: Memory and compounding
Each loop should persist:
- what was tried
- what succeeded
- what failed
- why it failed
- which experiment templates exposed weakness
- what should be tried next

### Layer 3: Solver-backed deepening
If a domain becomes important enough, add a richer verification layer through a sidecar or isolated solver path.

Do **not** contaminate the core engine with fragile runtime or environment complexity unless the payoff is clear.

### Layer 4: Shared prior later
Only after enough benchmark receipts exist should the system evolve toward a broader learned prior across domains.

---

## Implementation Principles

When making code changes, optimize for:

- clarity
- repeatability
- benchmark quality
- realism
- conservative decision logic
- low hidden complexity
- long-term composability

Avoid optimizing for:

- hype
- breadth for its own sake
- novelty theater
- one-off demos
- fragile integrations
- magical abstractions
- generic "AI agent" complexity

---

## Invariants

These are core project invariants and should be preserved unless there is a strong reason and explicit discussion to change them.

### Promotion invariants
- Maximum **1 promoted candidate per run**
- Optional **1 alternate only under strict conditions** (different family, near-threshold score)
- Promotion should remain conservative
- Hard-fail logic must remain active and meaningful
- Stress resilience gate for promotion (battery: >= 0.40)
- Regime-specificity gate: no extreme component imbalance in score

### Benchmark invariants
- Benchmark domains must remain **offline-safe** (no API keys required)
- Benchmark domains must have:
  - fixed templates
  - explicit scorecards
  - realism/reference checks (held-out commercial device)
  - deterministic artifact output
- Benchmark outputs must follow the shared benchmark artifact contract (`domain_models.BENCHMARK_REPORT_REQUIRED_KEYS`)
- Deterministic with fixed seed — same seed produces same report

### Memory invariants
- Memory must influence proposal generation
- Failed directions are assets, not noise
- Proposal rationale should remain inspectable
- The system must preserve idea and experiment memory
- Battery-specific: fast-charge weakness, resistance growth weakness, and rate-tradeoff collapse are tracked separately

### Runtime invariants
- Artifact paths should remain predictable
- CLI behavior should remain consistent across domains
- Working tree should be left clean after a batch
- Broad production behavior should not be destabilized by narrow-domain work
- Production DB: `runtime/db/scires.db`
- Always `source .env` before running (sets `BT_EMBEDDING_MODEL` and `OLLAMA_MODEL`)

---

## What Good Work Looks Like

A good batch should generally do one of the following:

1. Harden a benchmark domain
2. Improve realism priors
3. Improve robustness/stress evaluation
4. Improve promotion selectivity and caveat quality
5. Improve memory usefulness
6. Improve solver-backed validation
7. Improve benchmark/report consistency
8. Improve doc clarity and operational discipline

A good batch should **not** try to do everything at once.

---

## What To Defer By Default

Unless explicitly asked, do **not** introduce:

- new domains
- Omniverse integration
- PyBaMM rescue work if the runtime is incompatible
- Project Zero integration work
- UI or web app changes
- broad KG expansions
- plugin marketplaces
- giant benchmark frameworks
- paper-generation work
- broad refactors
- speculative future architecture

If a feature is exciting but does not improve:
- benchmark quality
- scientific credibility
- memory compounding
- solver-backed validation
- or commercial decision value

then it should probably be deferred.

---

## Domain Pack Standard

Every domain pack should follow the same structure.

### Required components
- `DomainSpec` (from `domain_models.py`)
- `MetricSpec` definitions (primary and secondary)
- `ExperimentTemplate` set
- candidate generation with bounded families and perturbation ranges
- cross-parameter plausibility checks
- experiment runner
- scoring with explicit weights and components
- hard fail gates
- caveat generation
- memory integration (idea memory + experiment memory)
- CLI support (`benchmark`, `run`, `dry-run`, `status`, `memory` subcommands)
- benchmark path
- unified benchmark artifact output

### Required behavior
A domain loop must be able to:

1. Generate bounded candidates from defined families
2. Run fixed experiments against each candidate
3. Extract explicit metrics
4. Compute composite score with inspectable components
5. Hard-fail invalid candidates (unphysical parameters, contradictory combinations)
6. Promote or reject conservatively
7. Persist memory (outcome-based + weakness-based)
8. Emit a benchmark-grade artifact with baseline comparison

---

## Candidate Generation Rules

Candidate generation should be:

- bounded (parameter ranges grounded in published data or commercial references)
- interpretable (family name, perturbation rationale, tradeoff risk documented)
- domain-grounded
- realistic enough to be useful
- diverse enough to explore meaningful tradeoffs
- subject to cross-parameter plausibility checks

Candidate generation should **not** be:

- fantasy invention
- unrestricted free-form mutation
- chemistry invention before the loop is ready
- driven only by score hacking

If realistic priors exist (e.g., commercial cell datasheets), use them.
If they do not exist yet, stay conservative and document assumptions explicitly.

---

## Scoring Rules

Every scorecard should be:

- explicit (named components with declared weights)
- inspectable (per-component breakdown in report)
- relatively small (8 or fewer components)
- tied to measurable outputs from experiment templates
- balanced with penalties and fail gates

Scores should not be allowed to hide:
- fragility
- thermal penalties
- regime-specific collapse
- implausible tradeoffs
- unrealistic candidates

A strong score is not enough by itself.
A candidate must also survive:
- robustness checks (worst-case across all stress templates)
- fail-gate logic (hard thresholds on critical metrics)
- realism/reference checks (within envelope of held-out commercial device)
- promotion discipline (stress resilience gate, regime-specificity gate)

---

## Memory Rules

Memory is a first-class asset.

Store and reuse:

### Idea memory
- candidate family
- proposal rationale
- decision outcome (promoted / rejected / hard-fail)
- lesson extracted
- whether the family is promising, weak, or fragile
- proposal tags: `[memory-supported]`, `[exploratory]`, `[recovery]`, `[retry-with-correction]`, `[stress-informed]`

### Experiment memory
- which template exposed weakness
- what metric failed
- which conditions caused collapse
- domain-specific weakness types (e.g., fast-charge weakness, resistance growth weakness)
- what should be tested next

Memory should improve future proposal quality in a way that is:
- simple
- auditable
- domain-relevant

Do not build giant opaque planners.
Prefer narrow, useful memory-guided adjustments (e.g., family weight up/down, weakness-informed tag).

---

## Solver Integration Rules

Solver-backed validation should be introduced only when it materially improves trust or decision value.

When adding a richer solver:

- isolate it if necessary
- avoid destabilizing the core runtime
- define a narrow experiment contract
- return structured artifacts
- use it to verify top candidates, not everything
- compare richer solver behavior to benchmark-loop behavior

The preferred pattern is often:
- fast benchmark loop first
- richer solver sidecar second

---

## Omniverse Policy

Omniverse is explicitly **deferred** for now.

It should only be introduced when:
- higher-fidelity simulation changes important decisions
- the benchmark loop has already proven value
- the richer simulation path is worth the complexity
- the outputs can be turned into deterministic, auditable artifacts

Omniverse should not be added for:
- novelty
- visuals
- architecture excitement
- premature "physics lab" branding

It is a later-stage escalation layer, not the current core.

---

## Commercial Orientation

This repository is part of a broader strategy to accelerate energy innovation.

The near-term commercial value comes from:
- validation
- benchmarked candidate generation
- simulation-backed technical assessment
- due diligence support
- trustworthy rejection and caveat logic

The long-term moat comes from:
- benchmark artifacts
- private receipts
- failed-candidate memory
- solver calibration history
- domain-specific priors
- eventually, a shared energy prior or energy foundation model

Therefore, code changes should support one or more of:
- better technical decisions
- faster evaluation cycles
- stronger scientific trust
- compounding private knowledge
- future reusable learning across energy domains

---

## How To Decide What To Build Next

Before implementing any meaningful feature, ask:

1. Does this improve a benchmark domain?
2. Does this improve solver-backed validation?
3. Does this improve memory compounding?
4. Does this improve commercial decision value?
5. Does this move us toward an energy foundation system?

If the answer to all five is "no," it probably should not be built now.

---

## Working Style

When implementing code:

- preserve production stability
- keep scope narrow
- prefer one disciplined batch over many scattered edits
- use one commit per contract when working in batch mode
- avoid unnecessary abstraction
- avoid framework bloat
- keep all changes benchmark-aware
- document deferred work clearly
- leave the working tree clean
- run relevant tests
- summarize what changed, why it matters, and what was intentionally deferred
- do not add Claude as a contributor in commits or project metadata
- use the Implementation Safety Harness (ISH) for every non-trivial code session
- do not commit code until the ISH gate passes

---

## Implementation Safety Harness (ISH)

This is the **standard autopilot workflow** for all implementation sessions.

### Agents

| Agent | Role |
|-------|------|
| **Opus** | Implements code. Runs verification. Initiates Codex review. Fixes blockers. Commits only after gate pass. |
| **GPT-5.2-Codex-mini** | Reviews every implementation session. Writes durable review artifact. Identifies blockers, warnings, suggestions. |

### Workflow

1. **Init session**: `python scripts/impl_session.py init --scope "..." [--risk medium] [--files ...]`
2. **Implement** within declared scope
3. **Verify**: `python scripts/impl_session.py verify`
4. **Codex review**: Opus sends diff + contracts to Codex, writes result via `write-review`
5. **Gate check**: `python scripts/impl_session.py gate` — must pass before commit
6. **Commit + push** only after gate passes
7. **Clean**: `python scripts/impl_session.py clean`

### Hard Rules

- Commit is **forbidden** until the gate passes (enforced by `.githooks/pre-commit`)
- Push is **forbidden** until commit passes all gates
- If Codex finds blockers, Opus must fix and rerun the gate
- Every code session produces a durable review artifact in `runtime/sessions/`
- Install hook once: `git config core.hooksPath .githooks`

### Full spec: `docs/IMPLEMENTATION_SAFETY_HARNESS.md`

---

## Preferred Batch Types

The most valuable batch types are:

- benchmark domain hardening
- realism prior improvement
- robustness/stress evaluation upgrades
- promotion and caveat tightening
- memory-guided search improvement
- solver sidecar integration
- artifact/report unification
- baseline freeze and regression discipline
- architecture/doc cleanup that reduces drift

The least valuable batch types are:

- speculative infrastructure
- broad platform expansion
- UI-first work
- premature high-fidelity simulation
- vague "agent intelligence" work without measurable loop improvements

---

## Current High-Level Roadmap

### Now
- stable broad engine (orchestrator, campaigns, policies, KG retrieval)
- PV benchmark (complete)
- battery benchmark v2 (complete, fast-charge and degradation-aware)
- unified benchmark/report contract
- memory-guided narrow-domain loops

### Next
- richer battery solver verification sidecar
- stronger fast-charge relevance
- future cathode-focused candidate layer (see `docs/BATTERY_V2_FORWARD_BRIDGE.md`)
- DC-DC as domain 3

### Later
- additional energy domains selectively
- solver sidecars in other domains
- shared latent energy prior
- future energy foundation model
- possible Omniverse escalation where justified

---

## Key Technical Context

### Stack
- Python 3.14, Pydantic v2, SQLite
- Ollama: `qwen3.5:9b-q4_K_M` (generation), `qwen3-embedding:4b` (embeddings, 2560-dim, Regime 2)
- Tests: `PYTHONPATH=. .venv/bin/pytest tests/test_breakthrough/`

### Embedding regime boundary
- Regime 1 (old): `nomic-embed-text` (768d) — up to commit `1b52a0f`
- Regime 2 (new): `qwen3-embedding:4b` (2560d) — commit `bbd7692` onward
- Never compare Regime 1 baselines to Regime 2 runs

### Production
- Champion policy: `evidence_diversity_v1`
- Default retrieval: `HybridKGEvidenceSource` (graph-native, promoted Phase 10K)
- Production DB: `runtime/db/scires.db`
- Always `source .env` before running

### Key file paths
- Domain models/contracts: `breakthrough_engine/domain_models.py`
- PV domain: `breakthrough_engine/pv_domain.py`, `breakthrough_engine/pv_loop.py`
- Battery domain: `breakthrough_engine/battery_domain.py`, `breakthrough_engine/battery_loop.py`
- Orchestrator: `breakthrough_engine/orchestrator.py`
- CLI: `breakthrough_engine/cli.py`
- Policy registry: `breakthrough_engine/policy_registry.py`
- Benchmark domains doc: `docs/BENCHMARK_DOMAINS.md`
- Battery forward bridge: `docs/BATTERY_V2_FORWARD_BRIDGE.md`
- Implementation Safety Harness: `scripts/impl_session.py`, `docs/IMPLEMENTATION_SAFETY_HARNESS.md`
- Session artifacts: `runtime/sessions/` (gitignored)
- Pre-commit hook: `.githooks/pre-commit`

---

## Final Instruction

Always remember:

Breakthrough Engine is not trying to become a generic autonomous scientist.

It is becoming an **energy foundation system**.

That means every code change should help the system become better at:
- turning energy questions into measurable loops
- running fixed experiments
- scoring outcomes conservatively
- learning from every result
- improving technical decision-making
- compounding into something more powerful over time
