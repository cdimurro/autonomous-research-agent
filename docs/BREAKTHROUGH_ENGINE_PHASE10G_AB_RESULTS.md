# Phase 10G: Limited Production Retrieval A/B — Results

**Date:** 2026-03-13
**Branch:** `breakthrough-engine-phase10g-retrieval-ab`
**Status:** COMPLETE

## Configuration

| Parameter | Value |
|-----------|-------|
| Campaigns per arm | 6 |
| Policy | evidence_diversity_v1 |
| Embedding | qwen3-embedding:4b (Regime 2) |
| Generation | qwen3.5:9b-q4_K_M |
| Domain | clean-energy |
| Total elapsed | ~3.5 hours |

## Arms

| Arm | Evidence Source | Generation | Graph Context |
|-----|----------------|------------|--------------|
| current | ExistingFindingsSource | flat template | No |
| graph_native | HybridKGEvidenceSource | graph-conditioned | Yes |

## Results

### Score Comparison

| Arm | Mean | Min | Max | Approval |
|-----|------|-----|-----|----------|
| Current | 0.9042 | 0.8855 | 0.923 | 100% |
| Graph Native | **0.9079** | 0.8855 | **0.933** | 100% |

### Champion Titles

**Current Arm:**
1. Biofouling-Resistant Perovskite-PV Thermal Management for Offshore Floaters
2. HEA Struts for Cryogenic Wind Turbine Superconducting Rotors
3. Self-Healing Elastomer Coatings for Offshore Turbine Rotor Hubs
4. 3D Printed Lattice Structures for Optimized PCM Heat Exchangers
5. Single-Atom Catalysts on Flexible Substrates for Low-Temp Electrolysis
6. Hierarchical HEA Structures for High-Stress Single-Atom Catalyst Supports

**Graph Native Arm:**
1. Defect-Engineered MXene-Supported Single-Atom Catalysts for CO2 Reduction
2. MXene-Reinforced AEM Electrolytes for High-Current Density H2 Production
3. Topological Insulator-Based Transparent Heaters for Smart Window De-icing
4. Directional Aerogel Interlayers for Isotope-Selective Hydrogen Purification
5. Hierarchical MXene-Sulfide Composites for Directional Waste Heat Harvesting
6. Self-Healing Elastomer Encapsulation for Perovskite Tandem Durability

### Review Labels: 24 total (24 approve, 0 defer, 0 reject)

### Decision: `continue_limited_ab`

See: `docs/BREAKTHROUGH_ENGINE_PHASE10G_SWITCH_DECISION.md`

## Artifacts

- `runtime/phase10g/arm_summary.json`
- `runtime/phase10g/comparison_summary.json`
- `runtime/phase10g/comparison_summary.md`
- `runtime/phase10g/champions.csv`
- `runtime/phase10g/campaign_metrics.csv`
- `runtime/phase10g/review_labels.csv`
- `runtime/phase10g/label_completion_summary.json`
- `runtime/phase10g/comparability_report.json`
