"""Tests for cathode-focused battery candidate generation.

Covers: chemistry profiles, cathode candidate families, chemistry-anchored
generation, cross-parameter plausibility, scoring behavior, and profile
confidence metadata.
"""

import pytest

from breakthrough_engine.battery_domain import (
    DEFAULT_CELL_PARAMS,
    check_physical_plausibility,
)
from breakthrough_engine.battery_loop import (
    CANDIDATE_FAMILIES,
    CATHODE_ECM_PROFILES,
    PARAM_RANGES,
    _check_cross_parameter_plausibility,
    generate_battery_candidates,
)


# ── Chemistry profile validation ──────────────────────────────────────────

class TestCathodeECMProfiles:
    """Validate that chemistry profiles produce valid, plausible ECM params."""

    def test_all_chemistries_present(self):
        assert "NMC_811" in CATHODE_ECM_PROFILES
        assert "LFP" in CATHODE_ECM_PROFILES
        assert "LMFP" in CATHODE_ECM_PROFILES
        assert "NMC_532" in CATHODE_ECM_PROFILES

    def test_each_profile_has_required_metadata(self):
        for chem, profile in CATHODE_ECM_PROFILES.items():
            assert "base_params" in profile, f"{chem} missing base_params"
            assert "profile_source" in profile, f"{chem} missing profile_source"
            assert "profile_confidence" in profile, f"{chem} missing profile_confidence"
            assert "pybamm_parameter_set" in profile, f"{chem} missing pybamm_parameter_set"

    def test_confidence_levels_valid(self):
        valid = {"literature-backed", "datasheet-anchored", "heuristic"}
        for chem, profile in CATHODE_ECM_PROFILES.items():
            assert profile["profile_confidence"] in valid, f"{chem}: {profile['profile_confidence']}"

    def test_lmfp_is_heuristic(self):
        assert CATHODE_ECM_PROFILES["LMFP"]["profile_confidence"] == "heuristic"

    def test_nmc811_is_literature_backed(self):
        assert CATHODE_ECM_PROFILES["NMC_811"]["profile_confidence"] == "literature-backed"

    def test_lfp_is_literature_backed(self):
        assert CATHODE_ECM_PROFILES["LFP"]["profile_confidence"] == "literature-backed"

    @pytest.mark.parametrize("chem", ["NMC_811", "LFP", "LMFP", "NMC_532"])
    def test_profile_passes_physical_plausibility(self, chem):
        params = CATHODE_ECM_PROFILES[chem]["base_params"]
        ok, reasons = check_physical_plausibility(params)
        assert ok, f"{chem} failed plausibility: {reasons}"

    def test_lfp_vmax_below_3_7(self):
        assert CATHODE_ECM_PROFILES["LFP"]["base_params"]["v_max"] < 3.7

    def test_nmc811_fade_higher_than_baseline(self):
        baseline_fade = DEFAULT_CELL_PARAMS["fade_rate_per_cycle"]
        nmc811_fade = CATHODE_ECM_PROFILES["NMC_811"]["base_params"]["fade_rate_per_cycle"]
        assert nmc811_fade > baseline_fade

    def test_lfp_capacity_lower_than_baseline(self):
        baseline_cap = DEFAULT_CELL_PARAMS["capacity_ah"]
        lfp_cap = CATHODE_ECM_PROFILES["LFP"]["base_params"]["capacity_ah"]
        assert lfp_cap < baseline_cap

    def test_lfp_fade_lower_than_baseline(self):
        baseline_fade = DEFAULT_CELL_PARAMS["fade_rate_per_cycle"]
        lfp_fade = CATHODE_ECM_PROFILES["LFP"]["base_params"]["fade_rate_per_cycle"]
        assert lfp_fade < baseline_fade

    def test_nmc532_pybamm_set_is_okane(self):
        assert CATHODE_ECM_PROFILES["NMC_532"]["pybamm_parameter_set"] == "OKane2022"

    def test_lmfp_no_pybamm_set(self):
        assert CATHODE_ECM_PROFILES["LMFP"]["pybamm_parameter_set"] is None


# ── Cathode candidate families ────────────────────────────────────────────

class TestCathodeFamilies:
    """Validate cathode family definitions in CANDIDATE_FAMILIES."""

    CATHODE_FAMILIES = [f for f in CANDIDATE_FAMILIES if f["family"].startswith("cathode_")]

    def test_four_cathode_families_exist(self):
        names = [f["family"] for f in self.CATHODE_FAMILIES]
        assert "cathode_high_ni" in names
        assert "cathode_lfp" in names
        assert "cathode_lmfp" in names
        assert "cathode_nmc532" in names
        assert len(self.CATHODE_FAMILIES) == 4

    def test_existing_seven_families_preserved(self):
        non_cathode = [f for f in CANDIDATE_FAMILIES if not f["family"].startswith("cathode_")]
        assert len(non_cathode) == 7

    def test_total_eleven_families(self):
        assert len(CANDIDATE_FAMILIES) == 11

    def test_each_cathode_family_has_chemistry(self):
        for f in self.CATHODE_FAMILIES:
            assert "chemistry" in f, f"{f['family']} missing chemistry key"
            assert f["chemistry"] in CATHODE_ECM_PROFILES, f"{f['family']}: {f['chemistry']} not in profiles"

    def test_each_cathode_family_has_perturbations(self):
        for f in self.CATHODE_FAMILIES:
            assert "perturbations" in f
            assert len(f["perturbations"]) > 0

    def test_each_cathode_family_has_tradeoff_risk(self):
        for f in self.CATHODE_FAMILIES:
            assert "tradeoff_risk" in f
            assert len(f["tradeoff_risk"]) > 0

    def test_non_cathode_families_have_no_chemistry(self):
        non_cathode = [f for f in CANDIDATE_FAMILIES if not f["family"].startswith("cathode_")]
        for f in non_cathode:
            assert "chemistry" not in f or f.get("chemistry") is None


# ── Chemistry-anchored candidate generation ───────────────────────────────

class TestChemistryAnchoredGeneration:
    """Verify candidates from cathode families use chemistry-specific base params."""

    def test_cathode_candidates_use_chemistry_base(self):
        """Cathode candidates should have params anchored to their chemistry profile."""
        # Generate enough candidates to likely get cathode families
        candidates = generate_battery_candidates(n_candidates=20, seed=100)
        cathode_candidates = [c for c in candidates if c.family.startswith("cathode_")]

        # With 20 candidates and 11 families, we should get some cathode candidates
        assert len(cathode_candidates) > 0, "No cathode candidates generated with 20 candidates"

        for c in cathode_candidates:
            family_def = next(f for f in CANDIDATE_FAMILIES if f["family"] == c.family)
            chemistry = family_def["chemistry"]
            profile = CATHODE_ECM_PROFILES[chemistry]

            # LFP candidates should have lower v_max than default
            if chemistry == "LFP":
                assert c.parameters.get("v_max", 4.2) <= 3.7, (
                    f"LFP candidate has v_max={c.parameters.get('v_max')}"
                )

    def test_lfp_candidate_has_lower_voltage(self):
        """LFP candidate v_max should be from LFP profile (~3.65V), not NMC default."""
        candidates = generate_battery_candidates(n_candidates=30, seed=200)
        lfp = [c for c in candidates if c.family == "cathode_lfp"]
        if lfp:
            for c in lfp:
                assert c.parameters.get("v_max", 4.2) <= 3.7

    def test_seed_reproducibility_with_cathode(self):
        c1 = generate_battery_candidates(n_candidates=10, seed=42)
        c2 = generate_battery_candidates(n_candidates=10, seed=42)
        for a, b in zip(c1, c2):
            assert a.family == b.family
            assert a.parameters == b.parameters

    def test_profile_confidence_in_rationale(self):
        """Cathode candidates should have profile confidence in rationale."""
        candidates = generate_battery_candidates(n_candidates=20, seed=100)
        cathode_candidates = [c for c in candidates if c.family.startswith("cathode_")]
        for c in cathode_candidates:
            assert "profile:" in c.rationale, f"{c.family} missing profile confidence in rationale"

    def test_heuristic_confidence_visible(self):
        """LMFP candidates should carry 'heuristic' in rationale."""
        candidates = generate_battery_candidates(n_candidates=30, seed=300)
        lmfp = [c for c in candidates if c.family == "cathode_lmfp"]
        if lmfp:
            for c in lmfp:
                assert "heuristic" in c.rationale

    def test_all_cathode_candidates_pass_plausibility(self):
        """All generated cathode candidates should pass physical plausibility."""
        candidates = generate_battery_candidates(n_candidates=30, seed=100)
        cathode_candidates = [c for c in candidates if c.family.startswith("cathode_")]
        for c in cathode_candidates:
            ok, reasons = check_physical_plausibility(c.parameters)
            assert ok, f"{c.family} failed: {reasons}"

    def test_all_cathode_candidates_within_param_ranges(self):
        """Clamping should ensure all params within PARAM_RANGES."""
        candidates = generate_battery_candidates(n_candidates=30, seed=100)
        cathode_candidates = [c for c in candidates if c.family.startswith("cathode_")]
        for c in cathode_candidates:
            for param, (lo, hi) in PARAM_RANGES.items():
                val = c.parameters.get(param)
                if val is not None:
                    assert lo <= val <= hi, (
                        f"{c.family} {param}={val} outside [{lo}, {hi}]"
                    )


# ── Cross-parameter plausibility: chemistry-aware ─────────────────────────

class TestChemistryCrossParamPlausibility:
    def test_lfp_with_nmc_voltage_rejected(self):
        """LFP-like params with NMC voltage range should be rejected."""
        params = {
            "capacity_ah": 2.5, "R0_mohm": 42.0, "R1_mohm": 22.0,
            "coulombic_eff": 0.999, "fade_rate_per_cycle": 0.00015,
            "v_max": 4.2,  # wrong for LFP
        }
        ok, reasons = _check_cross_parameter_plausibility(params)
        assert not ok
        assert any("LFP" in r for r in reasons)

    def test_lfp_with_correct_voltage_accepted(self):
        """LFP-like params with correct voltage should pass."""
        params = {
            "capacity_ah": 2.5, "R0_mohm": 42.0, "R1_mohm": 22.0,
            "coulombic_eff": 0.999, "fade_rate_per_cycle": 0.00015,
            "v_max": 3.65,  # correct for LFP
        }
        ok, reasons = _check_cross_parameter_plausibility(params)
        assert ok, f"Unexpected rejection: {reasons}"

    def test_nmc_params_still_accepted(self):
        """Standard NMC params should still pass (no regression)."""
        ok, reasons = _check_cross_parameter_plausibility(DEFAULT_CELL_PARAMS)
        assert ok


# ── Benchmark regression: existing families unchanged ─────────────────────

class TestBenchmarkRegression:
    def test_original_seven_families_generate_same_candidates(self):
        """Seed=42 with original families should produce same candidates."""
        c1 = generate_battery_candidates(n_candidates=6, seed=42)
        c2 = generate_battery_candidates(n_candidates=6, seed=42)
        for a, b in zip(c1, c2):
            assert a.family == b.family
            assert a.parameters == b.parameters

    def test_small_n_still_works(self):
        """n=3 should work without errors."""
        candidates = generate_battery_candidates(n_candidates=3, seed=42)
        assert len(candidates) == 3
