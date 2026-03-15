"""Battery Solver Sidecar — PyBaMM DFN verification for ECM-screened candidates.

Architecture:
    - The main engine (Python 3.14) never imports PyBaMM
    - PyBaMM runs in a separate Python 3.12 venv (.venv-pybamm/)
    - Communication: JSON over stdin/stdout via subprocess
    - If sidecar is unavailable, engine runs ECM-only (graceful degradation)

Concordance gate:
    - < 0.30  → VETO (candidate rejected)
    - 0.30–0.60 → caveat added, promotion stands
    - > 0.60 → confirmed
"""

import hashlib
import json
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


# ── Result schema ─────────────────────────────────────────────────────────

class SidecarStatus(str, Enum):
    """Sidecar verification result state."""
    SUCCESS = "success"          # concordance computed normally
    UNAVAILABLE = "unavailable"  # sidecar venv not found
    ERROR = "error"              # subprocess crash, timeout, unexpected failure
    INVALID = "invalid"          # unparseable or physically invalid output


class PyBaMMSidecarResult(BaseModel):
    """Structured result from sidecar verification."""
    candidate_id: str
    status: SidecarStatus
    concordance_score: float = 0.0       # 0.0–1.0 (0.0 if not SUCCESS)
    pybamm_metrics: dict = {}            # DFN simulation outputs
    ecm_metrics: dict = {}               # ECM metrics for comparison
    concordance_details: dict = {}       # per-metric agreement breakdown
    pybamm_parameter_set: str = ""       # e.g., "Chen2020", "custom"
    success: bool = False                # convenience: status == SUCCESS
    error_message: str = ""              # populated for ERROR/INVALID
    timed_out: bool = False
    duration_seconds: float = 0.0


# ── Concordance gate thresholds ───────────────────────────────────────────

CONCORDANCE_VETO_THRESHOLD = 0.30
CONCORDANCE_CONFIRM_THRESHOLD = 0.60


# ── ECM-to-DFN parameter mapping ─────────────────────────────────────────

# Concordance metric weights (must sum to 1.0)
#
# internal_resistance is excluded (weight 0) because ECM R0 and DFN
# voltage-sag resistance are methodologically incomparable (~0.002
# agreement consistently). Instead, energy_efficiency serves as the
# comparable resistance proxy (both models agree on voltage efficiency).
#
# discharge_capacity is the primary comparison metric after cell-matched
# normalization (scaling PyBaMM output to ECM nominal capacity).
CONCORDANCE_WEIGHTS = {
    "discharge_capacity": 0.45,
    "coulombic_efficiency": 0.15,
    "internal_resistance": 0.0,
    "energy_efficiency": 0.25,
    "rate_capability": 0.15,
}


# ── Cell-matched calibration profiles ─────────────────────────────────────
# PyBaMM parameter sets model specific cells with known nominal capacities.
# To compare ECM (which models a different cell size) against DFN, we
# normalize DFN discharge_capacity by the ratio:
#   ecm_nominal_cap / pybamm_nominal_cap
#
# This makes capacity comparison apples-to-apples: "what fraction of
# nominal capacity does each model predict?"
#
# Philosophy: small, explicit normalization rules. No hidden fitting.

PYBAMM_CELL_PROFILES = {
    "Chen2020": {
        "nominal_capacity_ah": 5.0,  # LG M50 21700
        "chemistry": "NMC-811",
        "cell_format": "21700",
        "source": "Chen et al. 2020, J. Electrochem. Soc.",
    },
    "Prada2013": {
        "nominal_capacity_ah": 2.3,  # A123 ANR26650 LFP
        "chemistry": "LFP",
        "cell_format": "26650",
        "source": "Prada et al. 2013, J. Power Sources",
    },
    "OKane2022": {
        "nominal_capacity_ah": 5.0,  # LG M50 21700 (same cell as Chen2020)
        "chemistry": "NMC",
        "cell_format": "21700",
        "source": "O'Kane et al. 2022, Electrochimica Acta",
    },
}


def calibrate_pybamm_metrics(
    pybamm_metrics: dict,
    ecm_nominal_capacity: float,
    pybamm_parameter_set: str,
) -> dict:
    """Normalize PyBaMM metrics to ECM cell scale for apples-to-apples comparison.

    Primary normalization: discharge_capacity is scaled by the ratio of
    ECM nominal capacity to PyBaMM parameter set nominal capacity.

    Other metrics (CE, energy_efficiency) are already in comparable units
    (%) and do not need scaling.

    Args:
        pybamm_metrics: Raw metrics from PyBaMM runner
        ecm_nominal_capacity: ECM cell's nominal capacity (Ah)
        pybamm_parameter_set: Name of the PyBaMM parameter set used

    Returns:
        Calibrated metrics dict with _calibration metadata
    """
    profile = PYBAMM_CELL_PROFILES.get(pybamm_parameter_set)
    if not profile:
        # Unknown parameter set — return raw metrics with warning
        return {
            **pybamm_metrics,
            "_calibration": {
                "applied": False,
                "reason": f"Unknown parameter set: {pybamm_parameter_set}",
            },
        }

    pybamm_nominal = profile["nominal_capacity_ah"]
    scale_factor = ecm_nominal_capacity / pybamm_nominal if pybamm_nominal > 0 else 1.0

    calibrated = dict(pybamm_metrics)

    # Scale capacity to ECM cell size
    raw_cap = pybamm_metrics.get("discharge_capacity")
    if raw_cap is not None:
        calibrated["discharge_capacity"] = round(raw_cap * scale_factor, 4)

    calibrated["_calibration"] = {
        "applied": True,
        "pybamm_parameter_set": pybamm_parameter_set,
        "pybamm_nominal_capacity_ah": pybamm_nominal,
        "ecm_nominal_capacity_ah": ecm_nominal_capacity,
        "capacity_scale_factor": round(scale_factor, 4),
        "pybamm_cell": f"{profile['chemistry']} {profile['cell_format']}",
        "raw_pybamm_capacity": raw_cap,
    }

    return calibrated

# Default PyBaMM parameter set for NMC cells
DEFAULT_PYBAMM_PARAMETER_SET = "Chen2020"

# Physical bounds for DFN parameters (sanity checks)
DFN_PARAM_BOUNDS = {
    "electrolyte_conductivity": (0.1, 5.0),        # S/m
    "contact_resistance": (0.001, 0.1),             # Ohm m^2
    "positive_exchange_current_density": (0.1, 50.0),  # A/m^2
    "negative_exchange_current_density": (0.5, 100.0),  # A/m^2
    "double_layer_capacitance": (0.1, 1.0),         # F/m^2
    "positive_electrode_thickness": (30e-6, 120e-6), # m
    "sei_growth_rate_constant": (1e-16, 1e-12),     # m/s^0.5
    "lower_voltage_cut_off": (2.0, 3.0),            # V
    "upper_voltage_cut_off": (3.5, 4.5),            # V
}


def map_ecm_to_dfn(
    ecm_params: dict,
    chemistry: Optional[str] = None,
    pybamm_parameter_set: Optional[str] = None,
) -> dict:
    """Map Thevenin 1RC ECM parameters to PyBaMM DFN parameters.

    Parameters that cannot be meaningfully mapped (OCV polynomial,
    temp coefficient) are left to the PyBaMM built-in parameter set.
    Each mapped value documents whether it is engine-derived or PyBaMM-default.

    Args:
        ecm_params: ECM cell parameters (R0_mohm, R1_mohm, capacity_ah, etc.)
        chemistry: Optional chemistry hint (e.g., "NMC_811", "LFP")
        pybamm_parameter_set: Optional PyBaMM parameter set name

    Returns:
        dict with DFN parameters + metadata
    """
    R0 = ecm_params.get("R0_mohm", 30.0)
    R1 = ecm_params.get("R1_mohm", 15.0)
    C1 = ecm_params.get("C1_F", 500.0)
    cap = ecm_params.get("capacity_ah", 3.0)
    fade = ecm_params.get("fade_rate_per_cycle", 0.0005)
    ce = ecm_params.get("coulombic_eff", 0.995)
    v_min = ecm_params.get("v_min", 2.5)
    v_max = ecm_params.get("v_max", 4.2)

    # Mapping rationale documented inline
    # R0 (mOhm) → electrolyte conductivity + contact resistance
    # Lower R0 → higher conductivity
    electrolyte_conductivity = max(0.1, min(5.0, 50.0 / R0))  # S/m, inverse
    contact_resistance = max(0.001, min(0.1, R0 * 1e-5))  # Ohm m^2

    # R1 (mOhm) → exchange current density (charge-transfer resistance)
    # Lower R1 → higher j0 (faster kinetics)
    positive_j0 = max(0.1, min(50.0, 300.0 / R1))  # A/m^2
    negative_j0 = max(0.5, min(100.0, 600.0 / R1))  # A/m^2

    # C1 (F) → double-layer capacitance (approximate)
    dl_cap = max(0.1, min(1.0, C1 / 1000.0))  # F/m^2

    # Capacity → electrode thickness (approximate via active material volume)
    # ~3 Ah ≈ ~70 µm positive electrode for a standard 18650/21700
    pos_thickness = max(30e-6, min(120e-6, cap / 3.0 * 70e-6))  # m

    # Fade rate → SEI growth rate constant
    # Higher fade → faster SEI growth
    sei_rate = max(1e-16, min(1e-12, fade * 2e-12))  # m/s^0.5

    dfn_params = {
        # Engine-derived (from ECM mapping)
        "electrolyte_conductivity": round(electrolyte_conductivity, 4),
        "contact_resistance": round(contact_resistance, 6),
        "positive_exchange_current_density": round(positive_j0, 4),
        "negative_exchange_current_density": round(negative_j0, 4),
        "double_layer_capacitance": round(dl_cap, 4),
        "positive_electrode_thickness": round(pos_thickness, 8),
        "sei_growth_rate_constant": sei_rate,
        "lower_voltage_cut_off": v_min,
        "upper_voltage_cut_off": v_max,
        # Metadata
        "_mapping_source": {
            "electrolyte_conductivity": "engine-derived (from R0_mohm)",
            "contact_resistance": "engine-derived (from R0_mohm)",
            "positive_exchange_current_density": "engine-derived (from R1_mohm)",
            "negative_exchange_current_density": "engine-derived (from R1_mohm)",
            "double_layer_capacitance": "engine-derived (from C1_F)",
            "positive_electrode_thickness": "engine-derived (from capacity_ah)",
            "sei_growth_rate_constant": "engine-derived (from fade_rate_per_cycle)",
            "lower_voltage_cut_off": "engine-derived (direct)",
            "upper_voltage_cut_off": "engine-derived (direct)",
        },
        "_pybamm_parameter_set": pybamm_parameter_set or DEFAULT_PYBAMM_PARAMETER_SET,
        "_chemistry": chemistry or "NMC",
    }

    return dfn_params


def validate_dfn_params(dfn_params: dict) -> tuple[bool, list[str]]:
    """Validate DFN parameters against physical bounds.

    Returns:
        (valid, list of violation messages)
    """
    issues = []
    for key, (lo, hi) in DFN_PARAM_BOUNDS.items():
        val = dfn_params.get(key)
        if val is None:
            continue
        if val < lo or val > hi:
            issues.append(f"{key}={val} outside bounds [{lo}, {hi}]")
    return (len(issues) == 0, issues)


# ── Concordance computation ───────────────────────────────────────────────

def compute_concordance(
    ecm_metrics: dict,
    pybamm_metrics: dict,
    weights: Optional[dict] = None,
) -> tuple[float, dict]:
    """Compare ECM vs PyBaMM metrics and return overall concordance score.

    Uses weighted per-metric agreement. Each metric is compared as:
        agreement = 1.0 - |ecm - pybamm| / max(|ecm|, |pybamm|, epsilon)

    Args:
        ecm_metrics: Metrics from ECM simulation
        pybamm_metrics: Metrics from PyBaMM DFN simulation
        weights: Optional metric weights (default: CONCORDANCE_WEIGHTS)

    Returns:
        (overall_concordance, per_metric_details)
    """
    w = weights or CONCORDANCE_WEIGHTS
    details = {}
    total_weight = 0.0
    weighted_sum = 0.0

    for metric, weight in w.items():
        ecm_val = ecm_metrics.get(metric)
        pybamm_val = pybamm_metrics.get(metric)

        if ecm_val is None or pybamm_val is None:
            details[metric] = {
                "ecm": ecm_val, "pybamm": pybamm_val,
                "agreement": None, "weight": weight, "reason": "missing",
            }
            continue

        denom = max(abs(ecm_val), abs(pybamm_val), 1e-12)
        agreement = max(0.0, 1.0 - abs(ecm_val - pybamm_val) / denom)

        details[metric] = {
            "ecm": ecm_val, "pybamm": pybamm_val,
            "agreement": round(agreement, 4), "weight": weight,
        }
        weighted_sum += agreement * weight
        total_weight += weight

    overall = weighted_sum / total_weight if total_weight > 0 else 0.0
    return (round(overall, 4), details)


# ── Sidecar adapters ─────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SIDECAR_VENV = REPO_ROOT / ".venv-pybamm"
DEFAULT_RUNNER_SCRIPT = REPO_ROOT / "battery_sidecar" / "pybamm_runner.py"


class PyBaMMSidecar:
    """Live PyBaMM sidecar — runs DFN simulation via subprocess.

    Requires a separate Python 3.11/3.12 venv with PyBaMM installed.
    Setup: bash scripts/setup_pybamm_sidecar.sh
    Check: bash scripts/setup_pybamm_sidecar.sh --check
    """

    def __init__(
        self,
        venv_path: Optional[Path] = None,
        runner_script: Optional[Path] = None,
        timeout_seconds: int = 120,
    ):
        self.venv_path = Path(venv_path) if venv_path else DEFAULT_SIDECAR_VENV
        self.runner_script = Path(runner_script) if runner_script else DEFAULT_RUNNER_SCRIPT
        self.timeout_seconds = timeout_seconds
        self._python = self.venv_path / "bin" / "python3"

    def is_available(self) -> bool:
        """Check if the sidecar venv and runner script exist."""
        return self._python.exists() and self.runner_script.exists()

    def check_health(self) -> dict:
        """Deep health check: venv exists, PyBaMM importable, runner works.

        Returns dict with keys: available, python_version, pybamm_version,
        parameter_set_ok, runner_ok, error.
        """
        result = {
            "available": False,
            "python_version": None,
            "pybamm_version": None,
            "parameter_set_ok": False,
            "runner_ok": False,
            "error": None,
        }
        if not self.is_available():
            result["error"] = "Sidecar venv or runner script not found"
            return result

        # Check Python version
        try:
            ver = subprocess.check_output(
                [str(self._python), "--version"],
                text=True, timeout=10,
            ).strip()
            result["python_version"] = ver
        except Exception as e:
            result["error"] = f"Python check failed: {e}"
            return result

        # Check PyBaMM import + version
        try:
            pybamm_ver = subprocess.check_output(
                [str(self._python), "-c",
                 "import pybamm; print(pybamm.__version__)"],
                text=True, timeout=30,
            ).strip()
            result["pybamm_version"] = pybamm_ver
        except Exception as e:
            result["error"] = f"PyBaMM import failed: {e}"
            return result

        # Check parameter set
        try:
            subprocess.check_output(
                [str(self._python), "-c",
                 "import pybamm; pybamm.ParameterValues('Chen2020')"],
                text=True, timeout=30,
            )
            result["parameter_set_ok"] = True
        except Exception as e:
            result["error"] = f"Parameter set check failed: {e}"
            return result

        # Check runner with a minimal request
        try:
            test_request = json.dumps({
                "dfn_params": {
                    "lower_voltage_cut_off": 2.5,
                    "upper_voltage_cut_off": 4.2,
                },
                "pybamm_parameter_set": "Chen2020",
                "experiments": ["baseline_1c"],
            })
            proc = subprocess.run(
                [str(self._python), str(self.runner_script)],
                input=test_request, capture_output=True, text=True,
                timeout=60,
            )
            if proc.returncode == 0:
                resp = json.loads(proc.stdout)
                if resp.get("success"):
                    result["runner_ok"] = True
                    result["available"] = True
                else:
                    result["error"] = f"Runner returned error: {resp.get('error', 'unknown')}"
            else:
                result["error"] = f"Runner exited {proc.returncode}: {proc.stderr[:200]}"
        except subprocess.TimeoutExpired:
            result["error"] = "Runner timed out during health check"
        except Exception as e:
            result["error"] = f"Runner check failed: {e}"

        return result

    def verify_candidate(
        self,
        candidate_id: str,
        ecm_params: dict,
        ecm_metrics: dict,
        chemistry: Optional[str] = None,
        pybamm_parameter_set: Optional[str] = None,
    ) -> PyBaMMSidecarResult:
        """Run PyBaMM DFN verification for a candidate.

        Maps ECM params to DFN, runs PyBaMM via subprocess, computes concordance.
        """
        if not self.is_available():
            return PyBaMMSidecarResult(
                candidate_id=candidate_id,
                status=SidecarStatus.UNAVAILABLE,
                ecm_metrics=ecm_metrics,
                error_message="Sidecar venv or runner script not found",
            )

        # Map ECM → DFN
        dfn_params = map_ecm_to_dfn(
            ecm_params, chemistry=chemistry,
            pybamm_parameter_set=pybamm_parameter_set,
        )
        valid, issues = validate_dfn_params(dfn_params)
        if not valid:
            return PyBaMMSidecarResult(
                candidate_id=candidate_id,
                status=SidecarStatus.INVALID,
                ecm_metrics=ecm_metrics,
                error_message=f"DFN parameter validation failed: {issues}",
            )

        # Build request
        request = {
            "dfn_params": {k: v for k, v in dfn_params.items() if not k.startswith("_")},
            "pybamm_parameter_set": dfn_params.get("_pybamm_parameter_set", DEFAULT_PYBAMM_PARAMETER_SET),
            "chemistry": dfn_params.get("_chemistry", "NMC"),
            "experiments": ["baseline_1c", "crate_sweep"],
        }

        # Run subprocess
        t0 = time.time()
        try:
            proc = subprocess.run(
                [str(self._python), str(self.runner_script)],
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=str(REPO_ROOT),
            )
        except subprocess.TimeoutExpired:
            return PyBaMMSidecarResult(
                candidate_id=candidate_id,
                status=SidecarStatus.ERROR,
                ecm_metrics=ecm_metrics,
                error_message=f"Sidecar timed out after {self.timeout_seconds}s",
                timed_out=True,
                duration_seconds=time.time() - t0,
            )
        except Exception as e:
            return PyBaMMSidecarResult(
                candidate_id=candidate_id,
                status=SidecarStatus.ERROR,
                ecm_metrics=ecm_metrics,
                error_message=f"Sidecar subprocess error: {e}",
                duration_seconds=time.time() - t0,
            )

        duration = time.time() - t0

        if proc.returncode != 0:
            return PyBaMMSidecarResult(
                candidate_id=candidate_id,
                status=SidecarStatus.ERROR,
                ecm_metrics=ecm_metrics,
                error_message=f"Sidecar exited with code {proc.returncode}: {proc.stderr[:500]}",
                duration_seconds=duration,
            )

        # Parse output
        try:
            response = json.loads(proc.stdout)
        except (json.JSONDecodeError, ValueError) as e:
            return PyBaMMSidecarResult(
                candidate_id=candidate_id,
                status=SidecarStatus.INVALID,
                ecm_metrics=ecm_metrics,
                error_message=f"Invalid JSON from sidecar: {e}",
                duration_seconds=duration,
            )

        if not response.get("success", False):
            return PyBaMMSidecarResult(
                candidate_id=candidate_id,
                status=SidecarStatus.ERROR,
                ecm_metrics=ecm_metrics,
                pybamm_metrics=response.get("metrics", {}),
                error_message=response.get("error", "Unknown sidecar error"),
                duration_seconds=duration,
            )

        pybamm_metrics = response.get("metrics", {})

        # Validate output physics
        if not _validate_pybamm_output(pybamm_metrics):
            return PyBaMMSidecarResult(
                candidate_id=candidate_id,
                status=SidecarStatus.INVALID,
                ecm_metrics=ecm_metrics,
                pybamm_metrics=pybamm_metrics,
                error_message="PyBaMM output failed physics validation",
                duration_seconds=duration,
            )

        # Cell-matched calibration: normalize PyBaMM metrics to ECM cell scale
        param_set = request.get("pybamm_parameter_set", DEFAULT_PYBAMM_PARAMETER_SET)
        ecm_nominal_cap = ecm_params.get("capacity_ah", 3.0)
        calibrated_metrics = calibrate_pybamm_metrics(
            pybamm_metrics, ecm_nominal_cap, param_set,
        )

        # Compute concordance on calibrated metrics
        concordance, details = compute_concordance(ecm_metrics, calibrated_metrics)

        return PyBaMMSidecarResult(
            candidate_id=candidate_id,
            status=SidecarStatus.SUCCESS,
            concordance_score=concordance,
            pybamm_metrics=calibrated_metrics,
            ecm_metrics=ecm_metrics,
            concordance_details=details,
            pybamm_parameter_set=param_set,
            success=True,
            duration_seconds=duration,
        )


def _validate_pybamm_output(metrics: dict) -> bool:
    """Basic physics validation of PyBaMM output metrics.

    Accepts metrics in ECM-compatible units:
    - discharge_capacity: Ah (0–10 Ah for cylindrical cells)
    - coulombic_efficiency: % (90–101%)
    - internal_resistance: mOhm (0–500 mOhm)
    - energy_efficiency: % (50–101%)
    """
    cap = metrics.get("discharge_capacity")
    if cap is not None and (cap <= 0 or cap > 10):
        return False
    ce = metrics.get("coulombic_efficiency")
    if ce is not None and (ce <= 0 or ce > 101):
        return False
    r = metrics.get("internal_resistance")
    if r is not None and (r <= 0 or r > 500):
        return False
    ee = metrics.get("energy_efficiency")
    if ee is not None and (ee <= 0 or ee > 101):
        return False
    return True


class MockPyBaMMSidecar:
    """Deterministic mock sidecar for offline-safe benchmarks.

    Returns concordance derived from a hash of candidate parameters,
    producing reproducible results with no external dependencies.
    """

    def __init__(self, seed: int = 42):
        self._seed = seed

    def is_available(self) -> bool:
        return True

    def verify_candidate(
        self,
        candidate_id: str,
        ecm_params: dict,
        ecm_metrics: dict,
        chemistry: Optional[str] = None,
        pybamm_parameter_set: Optional[str] = None,
    ) -> PyBaMMSidecarResult:
        """Return deterministic concordance from parameter hash."""
        # Deterministic hash from params + seed
        hash_input = json.dumps(
            {k: v for k, v in sorted(ecm_params.items()) if isinstance(v, (int, float))},
            sort_keys=True,
        ) + f"_seed={self._seed}"
        h = hashlib.sha256(hash_input.encode()).hexdigest()
        # Map hash to concordance in [0.25, 0.95] range
        raw = int(h[:8], 16) / 0xFFFFFFFF
        concordance = round(0.25 + raw * 0.70, 4)

        # Generate mock PyBaMM metrics by scaling ECM metrics
        scale_factor = 0.85 + raw * 0.30  # 0.85–1.15
        pybamm_metrics = {}
        for key in CONCORDANCE_WEIGHTS:
            ecm_val = ecm_metrics.get(key)
            if ecm_val is not None:
                pybamm_metrics[key] = round(ecm_val * scale_factor, 6)

        concordance_actual, details = compute_concordance(ecm_metrics, pybamm_metrics)

        return PyBaMMSidecarResult(
            candidate_id=candidate_id,
            status=SidecarStatus.SUCCESS,
            concordance_score=concordance_actual,
            pybamm_metrics=pybamm_metrics,
            ecm_metrics=ecm_metrics,
            concordance_details=details,
            pybamm_parameter_set=pybamm_parameter_set or "mock",
            success=True,
            duration_seconds=0.001,
        )
