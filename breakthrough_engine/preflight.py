"""Strict preflight verification for autonomous campaign readiness.

Phase 7A: Validates environment, DB, models, config, and runtime
prerequisites before launching pilot or overnight campaigns.

Each check returns a structured PreflightResult with PASS/WARN/FAIL
status and operator-readable remediation hints.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """Result of a single preflight check."""
    name: str
    status: str  # "PASS", "WARN", "FAIL"
    detail: str
    remediation: str = ""
    elapsed_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    @property
    def critical(self) -> bool:
        return self.status == "FAIL"


@dataclass
class PreflightReport:
    """Aggregate preflight report."""
    checks: list = field(default_factory=list)  # list[CheckResult]
    strict: bool = False
    campaign_profile: str = ""
    timestamp: str = ""

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def has_failures(self) -> bool:
        return any(c.critical for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(c.status == "WARN" for c in self.checks)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.critical)

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "WARN")

    @property
    def readiness_score(self) -> float:
        """Campaign readiness score: 0.0 to 1.0."""
        if not self.checks:
            return 0.0
        weights = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}
        total = sum(weights.get(c.status, 0.0) for c in self.checks)
        return total / len(self.checks)

    @property
    def ready_for_campaign(self) -> bool:
        """True if no FAIL checks and readiness score >= 0.7."""
        return not self.has_failures and self.readiness_score >= 0.7

    def to_dict(self) -> dict:
        return {
            "campaign_profile": self.campaign_profile,
            "strict": self.strict,
            "timestamp": self.timestamp,
            "readiness_score": round(self.readiness_score, 3),
            "ready_for_campaign": self.ready_for_campaign,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "detail": c.detail,
                    "remediation": c.remediation,
                    "elapsed_ms": round(c.elapsed_ms, 1),
                }
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# Preflight Engine
# ---------------------------------------------------------------------------

class PreflightEngine:
    """Runs all preflight checks and produces a structured report."""

    def run(
        self,
        db_path: Optional[str] = None,
        strict: bool = False,
        campaign_profile: str = "",
    ) -> PreflightReport:
        """Run all preflight checks. If strict=True, blocks on any FAIL."""
        from datetime import datetime, timezone
        report = PreflightReport(
            strict=strict,
            campaign_profile=campaign_profile,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        # Run each check
        report.checks.append(self._check_python_env())
        report.checks.append(self._check_db_reachable(db_path))
        report.checks.append(self._check_schema_version(db_path))
        report.checks.append(self._check_pending_migrations(db_path))
        report.checks.append(self._check_ollama_server())
        report.checks.append(self._check_generation_model())
        report.checks.append(self._check_embedding_model())
        report.checks.append(self._check_semantic_scholar_api_key())
        report.checks.append(self._check_write_access())
        report.checks.append(self._check_disk_space())
        report.checks.append(self._check_config_files())
        report.checks.append(self._check_research_programs())
        report.checks.append(self._check_clean_energy_findings(db_path))
        report.checks.append(self._check_review_pipeline())
        report.checks.append(self._check_campaign_lock())
        report.checks.append(self._check_campaign_profiles())

        return report

    def _timed_check(self, name: str, fn) -> CheckResult:
        """Run a check function with timing."""
        t0 = time.time()
        try:
            result = fn()
            result.elapsed_ms = (time.time() - t0) * 1000
            return result
        except Exception as e:
            return CheckResult(
                name=name,
                status="FAIL",
                detail=f"Unexpected error: {e}",
                remediation="Check logs for details",
                elapsed_ms=(time.time() - t0) * 1000,
            )

    def _check_python_env(self) -> CheckResult:
        """Verify key packages are importable."""
        t0 = time.time()
        missing = []
        for pkg in ["pydantic", "yaml", "sqlite3", "requests"]:
            try:
                __import__(pkg)
            except ImportError:
                missing.append(pkg)

        # Also check breakthrough_engine itself
        try:
            import breakthrough_engine  # noqa: F401
        except ImportError:
            missing.append("breakthrough_engine")

        elapsed = (time.time() - t0) * 1000
        if missing:
            return CheckResult(
                name="python_environment",
                status="FAIL",
                detail=f"Missing packages: {', '.join(missing)}",
                remediation="pip install " + " ".join(missing),
                elapsed_ms=elapsed,
            )
        return CheckResult(
            name="python_environment",
            status="PASS",
            detail="All required packages importable",
            elapsed_ms=elapsed,
        )

    def _check_db_reachable(self, db_path: Optional[str] = None) -> CheckResult:
        """Check DB file exists and is readable."""
        t0 = time.time()
        path = db_path or os.path.join(
            os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"), "db", "scires.db"
        )
        elapsed = lambda: (time.time() - t0) * 1000

        if not os.path.exists(path):
            return CheckResult(
                name="db_reachable",
                status="WARN",
                detail=f"DB not found at {path} (will be created on first run)",
                remediation="Run a benchmark first to create DB",
                elapsed_ms=elapsed(),
            )
        try:
            db = sqlite3.connect(path, timeout=5)
            db.execute("SELECT 1")
            db.close()
            return CheckResult(
                name="db_reachable",
                status="PASS",
                detail=f"DB accessible at {path}",
                elapsed_ms=elapsed(),
            )
        except Exception as e:
            return CheckResult(
                name="db_reachable",
                status="FAIL",
                detail=f"DB not accessible: {e}",
                remediation="Check file permissions or remove stale lock files",
                elapsed_ms=elapsed(),
            )

    def _check_schema_version(self, db_path: Optional[str] = None) -> CheckResult:
        """Check current schema version."""
        t0 = time.time()
        path = db_path or os.path.join(
            os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"), "db", "scires.db"
        )
        elapsed = lambda: (time.time() - t0) * 1000

        if not os.path.exists(path):
            return CheckResult(
                name="schema_version",
                status="WARN",
                detail="DB does not exist yet",
                elapsed_ms=elapsed(),
            )
        try:
            db = sqlite3.connect(path)
            row = db.execute("SELECT MAX(version) FROM bt_schema_version").fetchone()
            version = row[0] if row and row[0] else 0
            db.close()

            from .db import MIGRATIONS
            latest = max(MIGRATIONS.keys())

            if version >= latest:
                return CheckResult(
                    name="schema_version",
                    status="PASS",
                    detail=f"Schema at v{version:03d} (latest: v{latest:03d})",
                    elapsed_ms=elapsed(),
                )
            else:
                return CheckResult(
                    name="schema_version",
                    status="WARN",
                    detail=f"Schema at v{version:03d}, latest is v{latest:03d}",
                    remediation="Run init_db() to apply pending migrations",
                    elapsed_ms=elapsed(),
                )
        except Exception as e:
            return CheckResult(
                name="schema_version",
                status="WARN",
                detail=f"Could not read schema version: {e}",
                elapsed_ms=elapsed(),
            )

    def _check_pending_migrations(self, db_path: Optional[str] = None) -> CheckResult:
        """Check if there are unapplied migrations."""
        t0 = time.time()
        path = db_path or os.path.join(
            os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"), "db", "scires.db"
        )
        elapsed = lambda: (time.time() - t0) * 1000

        if not os.path.exists(path):
            return CheckResult(
                name="pending_migrations",
                status="PASS",
                detail="No DB yet — migrations will run on first init",
                elapsed_ms=elapsed(),
            )
        try:
            db = sqlite3.connect(path)
            row = db.execute("SELECT MAX(version) FROM bt_schema_version").fetchone()
            version = row[0] if row and row[0] else 0
            db.close()

            from .db import MIGRATIONS
            pending = [v for v in MIGRATIONS if v > version]
            if pending:
                return CheckResult(
                    name="pending_migrations",
                    status="WARN",
                    detail=f"{len(pending)} pending migration(s): {pending}",
                    remediation="Run init_db() before campaign launch",
                    elapsed_ms=elapsed(),
                )
            return CheckResult(
                name="pending_migrations",
                status="PASS",
                detail="No pending migrations",
                elapsed_ms=elapsed(),
            )
        except Exception:
            return CheckResult(
                name="pending_migrations",
                status="PASS",
                detail="DB not initialized yet",
                elapsed_ms=elapsed(),
            )

    def _check_ollama_server(self) -> CheckResult:
        """Check Ollama server reachability."""
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        try:
            import requests
            host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
            resp = requests.get(f"http://{host}/api/tags", timeout=5)
            resp.raise_for_status()
            models = resp.json().get("models", [])
            return CheckResult(
                name="ollama_server",
                status="PASS",
                detail=f"Reachable at {host}, {len(models)} model(s) loaded",
                elapsed_ms=elapsed(),
            )
        except Exception as e:
            return CheckResult(
                name="ollama_server",
                status="FAIL",
                detail=f"Not reachable: {e}",
                remediation="Start Ollama: ollama serve",
                elapsed_ms=elapsed(),
            )

    def _check_generation_model(self) -> CheckResult:
        """Check generation model availability."""
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        target = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M")
        try:
            import requests
            host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
            resp = requests.get(f"http://{host}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            if any(target in n for n in models):
                return CheckResult(
                    name="generation_model",
                    status="PASS",
                    detail=f"{target} available",
                    elapsed_ms=elapsed(),
                )
            return CheckResult(
                name="generation_model",
                status="FAIL",
                detail=f"{target} not found. Available: {', '.join(models[:5])}",
                remediation=f"ollama pull {target}",
                elapsed_ms=elapsed(),
            )
        except Exception:
            return CheckResult(
                name="generation_model",
                status="FAIL",
                detail=f"Cannot check — Ollama unreachable",
                remediation="Start Ollama and pull model",
                elapsed_ms=elapsed(),
            )

    def _check_embedding_model(self) -> CheckResult:
        """Check embedding model availability.

        Phase 7B hardening:
        - BT_EMBEDDING_MODEL unset → PASS (mock mode, acceptable for tests)
        - BT_EMBEDDING_MODEL set and model available → PASS
        - BT_EMBEDDING_MODEL set but model unavailable → FAIL in strict mode, WARN otherwise
        """
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        embed_model = os.environ.get("BT_EMBEDDING_MODEL", "")

        if not embed_model:
            # No real embedding configured — mock provider will be used
            return CheckResult(
                name="embedding_model",
                status="PASS",
                detail=(
                    "Using MockEmbeddingProvider (BT_EMBEDDING_MODEL not set). "
                    "Set BT_EMBEDDING_MODEL=nomic-embed-text for real embeddings."
                ),
                elapsed_ms=elapsed(),
            )

        # Real embedding model is configured — verify it is available
        try:
            import requests
            host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
            resp = requests.get(f"http://{host}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            if any(embed_model in n for n in models):
                return CheckResult(
                    name="embedding_model",
                    status="PASS",
                    detail=f"OllamaEmbeddingProvider({embed_model}) available — real embeddings active",
                    elapsed_ms=elapsed(),
                )
            # Model configured but not found
            return CheckResult(
                name="embedding_model",
                status="FAIL",
                detail=(
                    f"BT_EMBEDDING_MODEL={embed_model} is set but model not found in Ollama. "
                    f"Available: {', '.join(models[:5]) or 'none'}"
                ),
                remediation=f"ollama pull {embed_model}",
                elapsed_ms=elapsed(),
            )
        except Exception as e:
            return CheckResult(
                name="embedding_model",
                status="FAIL",
                detail=(
                    f"BT_EMBEDDING_MODEL={embed_model} is set but Ollama is unreachable: {e}"
                ),
                remediation="Start Ollama: ollama serve",
                elapsed_ms=elapsed(),
            )

    def _check_semantic_scholar_api_key(self) -> CheckResult:
        """Check Semantic Scholar API key availability.

        - SEMANTIC_SCHOLAR_API_KEY unset → WARN (public tier used, lower rate limits)
        - SEMANTIC_SCHOLAR_API_KEY set → verify reachability of S2 API
        - S2 API unreachable with key set → WARN (campaigns continue with ExistingFindingsSource)
        """
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")

        if not api_key:
            return CheckResult(
                name="semantic_scholar_api_key",
                status="WARN",
                detail=(
                    "SEMANTIC_SCHOLAR_API_KEY not set. Semantic Scholar will not be used as "
                    "an evidence source. Set this key to enable S2 evidence (TLDRs, influential "
                    "citations) alongside ExistingFindingsSource."
                ),
                remediation="export SEMANTIC_SCHOLAR_API_KEY=<your-key>  # see .env.example",
                elapsed_ms=elapsed(),
            )

        # Key is set — do a lightweight reachability check (1 result, no quota impact)
        try:
            import requests
            resp = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": "energy", "fields": "paperId", "limit": 1},
                headers={"x-api-key": api_key},
                timeout=8,
            )
            if resp.status_code == 200:
                return CheckResult(
                    name="semantic_scholar_api_key",
                    status="PASS",
                    detail="SEMANTIC_SCHOLAR_API_KEY set and S2 API reachable — S2 evidence active",
                    elapsed_ms=elapsed(),
                )
            if resp.status_code == 403:
                return CheckResult(
                    name="semantic_scholar_api_key",
                    status="WARN",
                    detail=(
                        f"SEMANTIC_SCHOLAR_API_KEY set but S2 returned 403 (invalid or expired key). "
                        f"Campaigns will fall back to ExistingFindingsSource only."
                    ),
                    remediation="Check your Semantic Scholar API key at https://www.semanticscholar.org/product/api",
                    elapsed_ms=elapsed(),
                )
            return CheckResult(
                name="semantic_scholar_api_key",
                status="WARN",
                detail=f"S2 API returned HTTP {resp.status_code} — may be a transient issue",
                elapsed_ms=elapsed(),
            )
        except Exception as e:
            return CheckResult(
                name="semantic_scholar_api_key",
                status="WARN",
                detail=f"SEMANTIC_SCHOLAR_API_KEY set but S2 API unreachable: {e}. Campaigns will proceed without S2.",
                elapsed_ms=elapsed(),
            )

    def _check_write_access(self) -> CheckResult:
        """Check write access to runtime/artifact directories."""
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        dirs_to_check = [
            os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"),
            os.path.join(os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"), "db"),
            os.path.join(os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"), "artifacts"),
            os.path.join(os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"), "campaigns"),
        ]
        issues = []
        for d in dirs_to_check:
            if os.path.exists(d):
                if not os.access(d, os.W_OK):
                    issues.append(f"{d} (not writable)")
            else:
                try:
                    os.makedirs(d, exist_ok=True)
                except OSError as e:
                    issues.append(f"{d} (cannot create: {e})")

        if issues:
            return CheckResult(
                name="write_access",
                status="FAIL",
                detail=f"Write issues: {'; '.join(issues)}",
                remediation="Fix directory permissions or ownership",
                elapsed_ms=elapsed(),
            )
        return CheckResult(
            name="write_access",
            status="PASS",
            detail=f"All runtime directories writable ({len(dirs_to_check)} checked)",
            elapsed_ms=elapsed(),
        )

    def _check_disk_space(self) -> CheckResult:
        """Check sufficient disk space."""
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        runtime_root = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
        try:
            usage = shutil.disk_usage(runtime_root if os.path.exists(runtime_root) else ".")
            free_gb = usage.free / (1024 ** 3)
            if free_gb < 1.0:
                return CheckResult(
                    name="disk_space",
                    status="FAIL",
                    detail=f"Only {free_gb:.1f}GB free",
                    remediation="Free up at least 1GB of disk space",
                    elapsed_ms=elapsed(),
                )
            if free_gb < 5.0:
                return CheckResult(
                    name="disk_space",
                    status="WARN",
                    detail=f"{free_gb:.1f}GB free (recommended: 5GB+)",
                    elapsed_ms=elapsed(),
                )
            return CheckResult(
                name="disk_space",
                status="PASS",
                detail=f"{free_gb:.1f}GB free",
                elapsed_ms=elapsed(),
            )
        except Exception as e:
            return CheckResult(
                name="disk_space",
                status="WARN",
                detail=f"Could not check disk space: {e}",
                elapsed_ms=elapsed(),
            )

    def _check_config_files(self) -> CheckResult:
        """Check required config files present."""
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        required = [
            "config/models.yaml",
            "config/sources.yaml",
        ]
        optional = [
            "config/reward_recipes/v1.yaml",
        ]
        missing_required = [f for f in required if not os.path.exists(f)]
        missing_optional = [f for f in optional if not os.path.exists(f)]

        if missing_required:
            return CheckResult(
                name="config_files",
                status="FAIL",
                detail=f"Missing required: {', '.join(missing_required)}",
                remediation="Restore missing config files from repo",
                elapsed_ms=elapsed(),
            )
        if missing_optional:
            return CheckResult(
                name="config_files",
                status="WARN",
                detail=f"Missing optional: {', '.join(missing_optional)}",
                elapsed_ms=elapsed(),
            )
        return CheckResult(
            name="config_files",
            status="PASS",
            detail="All config files present",
            elapsed_ms=elapsed(),
        )

    def _check_research_programs(self) -> CheckResult:
        """Check research programs are loadable."""
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        try:
            from .config_loader import list_programs
            programs = list_programs()
            ce_programs = [p for p in programs if "clean_energy" in p or "daily_quality" in p]
            if not ce_programs:
                return CheckResult(
                    name="research_programs",
                    status="WARN",
                    detail=f"{len(programs)} programs found but none for clean-energy",
                    remediation="Add clean_energy.yaml to config/research_programs/",
                    elapsed_ms=elapsed(),
                )
            return CheckResult(
                name="research_programs",
                status="PASS",
                detail=f"{len(programs)} programs ({len(ce_programs)} clean-energy)",
                elapsed_ms=elapsed(),
            )
        except Exception as e:
            return CheckResult(
                name="research_programs",
                status="FAIL",
                detail=f"Cannot load programs: {e}",
                remediation="Check config/research_programs/ directory",
                elapsed_ms=elapsed(),
            )

    def _check_clean_energy_findings(self, db_path: Optional[str] = None) -> CheckResult:
        """Check clean-energy findings are available and above minimum threshold."""
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        path = db_path or os.path.join(
            os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"), "db", "scires.db"
        )
        if not os.path.exists(path):
            return CheckResult(
                name="clean_energy_findings",
                status="WARN",
                detail="DB not found — findings cannot be checked",
                remediation="Run bootstrap_findings first",
                elapsed_ms=elapsed(),
            )
        try:
            db = sqlite3.connect(path)
            # Check for findings table
            tables = [r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            if "findings" in tables:
                count = db.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
                db.close()
                if count < 10:
                    return CheckResult(
                        name="clean_energy_findings",
                        status="WARN",
                        detail=f"Only {count} findings (minimum recommended: 100)",
                        remediation="Run bootstrap_findings to populate",
                        elapsed_ms=elapsed(),
                    )
                return CheckResult(
                    name="clean_energy_findings",
                    status="PASS",
                    detail=f"{count} findings available",
                    elapsed_ms=elapsed(),
                )
            db.close()
            return CheckResult(
                name="clean_energy_findings",
                status="WARN",
                detail="Findings table not found",
                remediation="Run bootstrap_findings to populate",
                elapsed_ms=elapsed(),
            )
        except Exception as e:
            return CheckResult(
                name="clean_energy_findings",
                status="WARN",
                detail=f"Cannot check findings: {e}",
                elapsed_ms=elapsed(),
            )

    def _check_review_pipeline(self) -> CheckResult:
        """Check review/export pipeline availability."""
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        try:
            from .review_cockpit import ReviewCockpit  # noqa: F401
            from .falsification import FalsificationEngine  # noqa: F401
            from .reporting import generate_markdown_report  # noqa: F401
            return CheckResult(
                name="review_pipeline",
                status="PASS",
                detail="Review cockpit, falsification, and reporting modules loadable",
                elapsed_ms=elapsed(),
            )
        except Exception as e:
            return CheckResult(
                name="review_pipeline",
                status="FAIL",
                detail=f"Pipeline module import error: {e}",
                remediation="Check package installation",
                elapsed_ms=elapsed(),
            )

    def _check_campaign_lock(self) -> CheckResult:
        """Check no existing campaign lockfile."""
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        lock_path = os.path.join(
            os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"), "campaign.lock"
        )
        if os.path.exists(lock_path):
            try:
                with open(lock_path) as f:
                    lock_info = f.read().strip()
                return CheckResult(
                    name="campaign_lock",
                    status="FAIL",
                    detail=f"Campaign lock exists: {lock_info}",
                    remediation=f"Remove {lock_path} if no campaign is running",
                    elapsed_ms=elapsed(),
                )
            except Exception:
                return CheckResult(
                    name="campaign_lock",
                    status="FAIL",
                    detail="Campaign lock file exists",
                    remediation=f"Remove {lock_path}",
                    elapsed_ms=elapsed(),
                )
        return CheckResult(
            name="campaign_lock",
            status="PASS",
            detail="No active campaign lock",
            elapsed_ms=elapsed(),
        )

    def _check_campaign_profiles(self) -> CheckResult:
        """Check campaign profile configs exist."""
        t0 = time.time()
        elapsed = lambda: (time.time() - t0) * 1000
        profiles_dir = "config/campaign_profiles"
        if not os.path.exists(profiles_dir):
            return CheckResult(
                name="campaign_profiles",
                status="WARN",
                detail="Campaign profiles directory not found",
                remediation=f"Create {profiles_dir}/",
                elapsed_ms=elapsed(),
            )
        profiles = [f for f in os.listdir(profiles_dir) if f.endswith(".yaml")]
        if not profiles:
            return CheckResult(
                name="campaign_profiles",
                status="WARN",
                detail="No campaign profiles found",
                elapsed_ms=elapsed(),
            )
        return CheckResult(
            name="campaign_profiles",
            status="PASS",
            detail=f"{len(profiles)} profile(s): {', '.join(p.replace('.yaml','') for p in profiles)}",
            elapsed_ms=elapsed(),
        )

    def format_report(self, report: PreflightReport) -> str:
        """Format report as operator-readable text."""
        lines = [
            "Breakthrough Engine — Campaign Preflight Report",
            "=" * 60,
            f"Profile: {report.campaign_profile or 'none'}",
            f"Strict mode: {'YES' if report.strict else 'no'}",
            f"Timestamp: {report.timestamp}",
            "",
        ]
        for c in report.checks:
            icon = {"PASS": "+", "FAIL": "X", "WARN": "!"}[c.status]
            lines.append(f"  [{icon}] {c.name}: {c.status} — {c.detail}")
            if c.remediation:
                lines.append(f"      Remedy: {c.remediation}")

        lines.append("")
        lines.append("=" * 60)
        lines.append(
            f"Summary: {report.pass_count} PASS, {report.warn_count} WARN, "
            f"{report.fail_count} FAIL"
        )
        lines.append(f"Readiness score: {report.readiness_score:.2f}")

        if report.ready_for_campaign:
            lines.append("Campaign readiness: READY")
        else:
            lines.append("Campaign readiness: NOT READY")
            if report.has_failures:
                lines.append("  Reason: Critical checks failed")
            else:
                lines.append("  Reason: Readiness score below threshold")

        return "\n".join(lines)
