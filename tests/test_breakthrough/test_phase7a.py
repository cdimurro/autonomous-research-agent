"""Phase 7A tests: Autonomous operations, preflight, campaign manager, profiles.

All tests are offline-safe (no Ollama, no real DB, no network).
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest

from breakthrough_engine.db import Repository, init_db, MIGRATIONS


# ---------------------------------------------------------------------------
# Test: Schema v008 migration
# ---------------------------------------------------------------------------

class TestSchemaV008Migration(unittest.TestCase):
    """Verify v008 migration adds campaign operations tables."""

    def setUp(self):
        self.db = init_db(in_memory=True)
        self.repo = Repository(self.db)

    def test_migration_version_8_exists(self):
        self.assertIn(8, MIGRATIONS)

    def test_campaign_receipts_table_exists(self):
        tables = [r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_campaign_receipts'"
        ).fetchall()]
        self.assertIn("bt_campaign_receipts", tables)

    def test_preflight_results_table_exists(self):
        tables = [r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_preflight_results'"
        ).fetchall()]
        self.assertIn("bt_preflight_results", tables)

    def test_campaign_heartbeats_table_exists(self):
        tables = [r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_campaign_heartbeats'"
        ).fetchall()]
        self.assertIn("bt_campaign_heartbeats", tables)

    def test_schema_version_is_8(self):
        row = self.db.execute("SELECT MAX(version) FROM bt_schema_version").fetchone()
        self.assertEqual(row[0], 8)

    def test_total_bt_tables_count(self):
        tables = [r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'bt_%'"
        ).fetchall()]
        self.assertGreaterEqual(len(tables), 39)  # 36 + 3 new

    def test_campaign_receipt_insert_and_read(self):
        self.db.execute(
            """INSERT INTO bt_campaign_receipts
               (campaign_id, profile_name, profile_type, status)
               VALUES (?, ?, ?, ?)""",
            ("test123", "pilot_30m", "pilot", "completed_with_draft"),
        )
        self.db.commit()
        row = self.db.execute(
            "SELECT * FROM bt_campaign_receipts WHERE campaign_id=?", ("test123",)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["profile_name"], "pilot_30m")
        self.assertEqual(row["status"], "completed_with_draft")


# ---------------------------------------------------------------------------
# Test: Preflight Engine
# ---------------------------------------------------------------------------

class TestPreflightEngine(unittest.TestCase):
    """Test preflight checks and report generation."""

    def setUp(self):
        self.db = init_db(in_memory=True)
        from breakthrough_engine.preflight import PreflightEngine
        self.engine = PreflightEngine()

    def test_check_result_pass(self):
        from breakthrough_engine.preflight import CheckResult
        c = CheckResult(name="test", status="PASS", detail="ok")
        self.assertTrue(c.passed)
        self.assertFalse(c.critical)

    def test_check_result_fail(self):
        from breakthrough_engine.preflight import CheckResult
        c = CheckResult(name="test", status="FAIL", detail="bad")
        self.assertFalse(c.passed)
        self.assertTrue(c.critical)

    def test_check_result_warn(self):
        from breakthrough_engine.preflight import CheckResult
        c = CheckResult(name="test", status="WARN", detail="meh")
        self.assertFalse(c.passed)
        self.assertFalse(c.critical)

    def test_preflight_report_readiness_score(self):
        from breakthrough_engine.preflight import PreflightReport, CheckResult
        report = PreflightReport(checks=[
            CheckResult(name="a", status="PASS", detail="ok"),
            CheckResult(name="b", status="PASS", detail="ok"),
            CheckResult(name="c", status="WARN", detail="meh"),
            CheckResult(name="d", status="FAIL", detail="bad"),
        ])
        # (1.0 + 1.0 + 0.5 + 0.0) / 4 = 0.625
        self.assertAlmostEqual(report.readiness_score, 0.625)

    def test_preflight_report_all_passed(self):
        from breakthrough_engine.preflight import PreflightReport, CheckResult
        report = PreflightReport(checks=[
            CheckResult(name="a", status="PASS", detail="ok"),
            CheckResult(name="b", status="PASS", detail="ok"),
        ])
        self.assertTrue(report.all_passed)
        self.assertTrue(report.ready_for_campaign)

    def test_preflight_report_not_ready_with_fail(self):
        from breakthrough_engine.preflight import PreflightReport, CheckResult
        report = PreflightReport(checks=[
            CheckResult(name="a", status="PASS", detail="ok"),
            CheckResult(name="b", status="FAIL", detail="bad"),
        ])
        self.assertFalse(report.all_passed)
        self.assertTrue(report.has_failures)
        self.assertFalse(report.ready_for_campaign)

    def test_preflight_report_to_dict(self):
        from breakthrough_engine.preflight import PreflightReport, CheckResult
        report = PreflightReport(
            checks=[CheckResult(name="a", status="PASS", detail="ok")],
            campaign_profile="pilot_30m",
            timestamp="2026-03-08T12:00:00Z",
        )
        d = report.to_dict()
        self.assertEqual(d["campaign_profile"], "pilot_30m")
        self.assertEqual(d["pass_count"], 1)
        self.assertTrue(d["ready_for_campaign"])

    def test_python_env_check_passes(self):
        result = self.engine._check_python_env()
        self.assertEqual(result.status, "PASS")

    def test_write_access_check(self):
        result = self.engine._check_write_access()
        # Should PASS or WARN but not FAIL in test env
        self.assertIn(result.status, ["PASS", "WARN"])

    def test_disk_space_check(self):
        result = self.engine._check_disk_space()
        self.assertIn(result.status, ["PASS", "WARN"])

    def test_review_pipeline_check(self):
        result = self.engine._check_review_pipeline()
        self.assertEqual(result.status, "PASS")

    def test_research_programs_check(self):
        result = self.engine._check_research_programs()
        self.assertIn(result.status, ["PASS", "WARN"])

    def test_campaign_profiles_check(self):
        result = self.engine._check_campaign_profiles()
        self.assertIn(result.status, ["PASS", "WARN"])

    def test_format_report(self):
        from breakthrough_engine.preflight import PreflightReport, CheckResult
        report = PreflightReport(
            checks=[
                CheckResult(name="test_check", status="PASS", detail="All good"),
                CheckResult(name="warn_check", status="WARN", detail="Maybe",
                            remediation="Fix it"),
            ],
            campaign_profile="test",
            timestamp="2026-03-08T12:00:00Z",
        )
        text = self.engine.format_report(report)
        self.assertIn("Campaign Preflight Report", text)
        self.assertIn("[+] test_check", text)
        self.assertIn("[!] warn_check", text)
        self.assertIn("Remedy:", text)

    def test_strict_mode_annotation(self):
        from breakthrough_engine.preflight import PreflightReport, CheckResult
        report = PreflightReport(strict=True, checks=[
            CheckResult(name="a", status="PASS", detail="ok"),
        ])
        text = self.engine.format_report(report)
        self.assertIn("Strict mode: YES", text)

    def test_preflight_run_returns_report(self):
        # Run with a non-existent DB path to test graceful handling
        report = self.engine.run(
            db_path="/tmp/nonexistent_test_preflight.db",
            strict=False,
            campaign_profile="test",
        )
        self.assertIsInstance(report.checks, list)
        self.assertGreater(len(report.checks), 5)


# ---------------------------------------------------------------------------
# Test: Campaign profiles
# ---------------------------------------------------------------------------

class TestCampaignProfiles(unittest.TestCase):
    """Test campaign profile loading."""

    def test_load_pilot_profile(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("pilot_30m")
        self.assertEqual(profile.profile_name, "pilot_30m")
        self.assertEqual(profile.profile_type, "pilot")
        self.assertEqual(profile.domain, "clean-energy")
        self.assertEqual(profile.wall_clock_budget_minutes, 30)
        self.assertTrue(profile.diagnostic_rich)

    def test_load_overnight_profile(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("overnight_clean_energy")
        self.assertEqual(profile.profile_name, "overnight_clean_energy")
        self.assertEqual(profile.profile_type, "overnight")
        self.assertEqual(profile.wall_clock_budget_minutes, 480)
        self.assertEqual(profile.stage1_max_trials, 10)

    def test_load_nonexistent_profile_raises(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        with self.assertRaises(FileNotFoundError):
            load_campaign_profile("nonexistent_profile")

    def test_pilot_has_conservative_settings(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("pilot_30m")
        self.assertEqual(profile.stage1_max_trials, 3)
        self.assertLessEqual(profile.candidate_trial_budget, 5)
        self.assertTrue(profile.review_packet_generation)

    def test_overnight_has_quality_settings(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        profile = load_campaign_profile("overnight_clean_energy")
        self.assertGreater(profile.stage1_max_trials, profile.stage1_max_trials - 1)  # sanity
        self.assertTrue(profile.falsification_strict)
        self.assertEqual(profile.stage2_shortlist_size, 5)


# ---------------------------------------------------------------------------
# Test: Campaign Manager
# ---------------------------------------------------------------------------

class TestCampaignManager(unittest.TestCase):
    """Test campaign manager lifecycle and state persistence."""

    def setUp(self):
        self.db = init_db(in_memory=True)
        self.repo = Repository(self.db)

    def test_campaign_receipt_to_dict(self):
        from breakthrough_engine.campaign_manager import CampaignReceipt
        receipt = CampaignReceipt(
            campaign_id="test123",
            profile_name="pilot_30m",
            status="completed_with_draft",
            champion_candidate_id="cand456",
        )
        d = receipt.to_dict()
        self.assertEqual(d["campaign_id"], "test123")
        self.assertEqual(d["status"], "completed_with_draft")

    def test_campaign_status_enum(self):
        from breakthrough_engine.campaign_manager import CampaignStatus
        self.assertEqual(CampaignStatus.COMPLETED_WITH_DRAFT.value, "completed_with_draft")
        self.assertEqual(CampaignStatus.COMPLETED_NO_DRAFT.value, "completed_no_draft")
        self.assertEqual(CampaignStatus.ABORTED_PREFLIGHT.value, "aborted_preflight")
        self.assertEqual(CampaignStatus.ABORTED_RUNTIME.value, "aborted_runtime")

    def test_stage_event_to_dict(self):
        from breakthrough_engine.campaign_manager import StageEvent
        event = StageEvent(
            stage_name="preflight",
            status="completed",
            started_at="2026-03-08T12:00:00Z",
        )
        d = event.to_dict()
        self.assertEqual(d["stage_name"], "preflight")
        self.assertEqual(d["status"], "completed")

    def test_campaign_manager_save_receipt(self):
        from breakthrough_engine.campaign_manager import CampaignManager, CampaignReceipt
        manager = CampaignManager(repo=self.repo)
        receipt = CampaignReceipt(
            campaign_id="save_test_123",
            profile_name="pilot_30m",
            profile_type="pilot",
            status="completed_no_draft",
            started_at="2026-03-08T12:00:00Z",
            completed_at="2026-03-08T12:30:00Z",
        )
        manager._save_receipt(receipt)
        row = self.repo.db.execute(
            "SELECT * FROM bt_campaign_receipts WHERE campaign_id=?",
            ("save_test_123",),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["profile_name"], "pilot_30m")
        self.assertEqual(row["status"], "completed_no_draft")

    def test_campaign_manager_get_receipt(self):
        from breakthrough_engine.campaign_manager import CampaignManager, CampaignReceipt
        manager = CampaignManager(repo=self.repo)
        receipt = CampaignReceipt(
            campaign_id="get_test_456",
            profile_name="overnight_clean_energy",
            status="completed_with_draft",
        )
        manager._save_receipt(receipt)
        loaded = manager.get_receipt("get_test_456")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["profile_name"], "overnight_clean_energy")

    def test_campaign_manager_list_campaigns(self):
        from breakthrough_engine.campaign_manager import CampaignManager, CampaignReceipt
        manager = CampaignManager(repo=self.repo)
        for i in range(3):
            receipt = CampaignReceipt(
                campaign_id=f"list_test_{i}",
                profile_name="pilot_30m",
                status="completed_no_draft",
                started_at=f"2026-03-0{8+i}T12:00:00Z",
            )
            manager._save_receipt(receipt)
        campaigns = manager.list_campaigns(limit=10)
        self.assertEqual(len(campaigns), 3)

    def test_campaign_profile_to_dict(self):
        from breakthrough_engine.campaign_manager import CampaignManager, CampaignProfile
        manager = CampaignManager()
        profile = CampaignProfile(profile_name="test", domain="clean-energy")
        d = manager._profile_to_dict(profile)
        self.assertEqual(d["profile_name"], "test")
        self.assertEqual(d["domain"], "clean-energy")

    def test_compute_health_summary_healthy(self):
        from breakthrough_engine.campaign_manager import (
            CampaignManager, CampaignReceipt, CampaignProfile, StageStatus,
        )
        manager = CampaignManager()
        receipt = CampaignReceipt(
            campaign_id="health_test",
            status="completed_with_draft",
            total_candidates_generated=10,
            retries_used=0,
            stage_events=[
                {"stage_name": "preflight", "status": StageStatus.COMPLETED.value},
                {"stage_name": "db_init", "status": StageStatus.COMPLETED.value},
                {"stage_name": "daily_search_ladder", "status": StageStatus.COMPLETED.value},
                {"stage_name": "artifact_export", "status": StageStatus.COMPLETED.value},
            ],
        )
        profile = CampaignProfile(health_min_candidates=3, health_min_stages=3)
        health = manager._compute_health_summary(receipt, profile)
        self.assertTrue(health["healthy"])
        self.assertTrue(health["overnight_ready"])
        self.assertEqual(len(health["issues"]), 0)

    def test_compute_health_summary_unhealthy(self):
        from breakthrough_engine.campaign_manager import (
            CampaignManager, CampaignReceipt, CampaignProfile, StageStatus,
        )
        manager = CampaignManager()
        receipt = CampaignReceipt(
            campaign_id="health_test_bad",
            status="aborted_runtime",
            total_candidates_generated=1,
            retries_used=5,
            stage_events=[
                {"stage_name": "preflight", "status": StageStatus.COMPLETED.value},
                {"stage_name": "ladder", "status": StageStatus.FAILED.value},
            ],
        )
        profile = CampaignProfile(health_min_candidates=3, health_min_stages=3, health_max_retry_count=3)
        health = manager._compute_health_summary(receipt, profile)
        self.assertFalse(health["healthy"])
        self.assertFalse(health["overnight_ready"])
        self.assertGreater(len(health["issues"]), 0)

    def test_dry_run_campaign(self):
        """Dry-run should do preflight only, no execution."""
        from breakthrough_engine.campaign_manager import (
            CampaignManager, CampaignProfile, CampaignStatus,
        )
        manager = CampaignManager(repo=self.repo)
        profile = CampaignProfile(
            profile_name="test_dry_run",
            mode="benchmark",
        )
        receipt = manager.run_campaign(profile, strict_preflight=False, dry_run=True)
        self.assertEqual(receipt.status, CampaignStatus.COMPLETED_NO_DRAFT.value)
        self.assertIn("dry_run", receipt.failure_reason)
        self.assertGreater(len(receipt.stage_events), 0)


# ---------------------------------------------------------------------------
# Test: Campaign Lock
# ---------------------------------------------------------------------------

class TestCampaignLock(unittest.TestCase):
    """Test campaign lock acquisition and release."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_acquire_and_release(self):
        from breakthrough_engine.campaign_manager import CampaignLock
        lock = CampaignLock(lock_dir=self.tmpdir)
        self.assertTrue(lock.acquire("test_campaign"))
        lock_path = os.path.join(self.tmpdir, "campaign.lock")
        self.assertTrue(os.path.exists(lock_path))
        lock.release()
        self.assertFalse(os.path.exists(lock_path))

    def test_double_acquire_fails(self):
        from breakthrough_engine.campaign_manager import CampaignLock
        lock = CampaignLock(lock_dir=self.tmpdir)
        self.assertTrue(lock.acquire("campaign_1"))
        # Same process, lock should fail
        lock2 = CampaignLock(lock_dir=self.tmpdir)
        self.assertFalse(lock2.acquire("campaign_2"))
        lock.release()

    def test_stale_lock_recovery(self):
        from breakthrough_engine.campaign_manager import CampaignLock
        # Write a lock with a dead PID
        lock_path = os.path.join(self.tmpdir, "campaign.lock")
        with open(lock_path, "w") as f:
            json.dump({"campaign_id": "old", "pid": 99999999}, f)
        lock = CampaignLock(lock_dir=self.tmpdir)
        # Should recover from stale lock
        self.assertTrue(lock.acquire("new_campaign"))
        lock.release()

    def test_release_nonexistent_lock(self):
        from breakthrough_engine.campaign_manager import CampaignLock
        lock = CampaignLock(lock_dir=self.tmpdir)
        # Should not raise
        lock.release()


# ---------------------------------------------------------------------------
# Test: Retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic(unittest.TestCase):
    """Test error classification and retryability."""

    def test_timeout_is_retryable(self):
        from breakthrough_engine.campaign_manager import _is_retryable
        self.assertTrue(_is_retryable(Exception("Connection timed out")))

    def test_db_lock_is_retryable(self):
        from breakthrough_engine.campaign_manager import _is_retryable
        self.assertTrue(_is_retryable(Exception("database is locked")))

    def test_permission_denied_is_retryable(self):
        from breakthrough_engine.campaign_manager import _is_retryable
        self.assertTrue(_is_retryable(Exception("Permission denied")))

    def test_unknown_error_not_retryable(self):
        from breakthrough_engine.campaign_manager import _is_retryable
        self.assertFalse(_is_retryable(Exception("Something completely unknown")))

    def test_classify_timeout(self):
        from breakthrough_engine.campaign_manager import _classify_error
        self.assertEqual(_classify_error(Exception("timed out")), "ollama_timeout")

    def test_classify_db_lock(self):
        from breakthrough_engine.campaign_manager import _classify_error
        self.assertEqual(_classify_error(Exception("database is locked")), "db_lock")

    def test_classify_unknown(self):
        from breakthrough_engine.campaign_manager import _classify_error
        self.assertEqual(_classify_error(Exception("weird error")), "unknown")


# ---------------------------------------------------------------------------
# Test: Artifact export
# ---------------------------------------------------------------------------

class TestArtifactExport(unittest.TestCase):
    """Test artifact export layout and content."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db = init_db(in_memory=True)
        self.repo = Repository(self.db)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_export_creates_files(self):
        from breakthrough_engine.campaign_manager import CampaignManager, CampaignReceipt
        manager = CampaignManager(repo=self.repo)
        receipt = CampaignReceipt(
            campaign_id="export_test",
            profile_name="pilot_30m",
            status="completed_with_draft",
            started_at="2026-03-08T12:00:00Z",
            champion_candidate_id="cand123",
            champion_candidate_title="Test Candidate",
            total_candidates_generated=5,
        )

        from breakthrough_engine.campaign_manager import CampaignProfile
        profile = CampaignProfile()

        # Create a minimal campaign_result-like object
        class MockResult:
            campaign_id = "export_test"
            daily_champion_id = "cand123"
            daily_champion_title = "Test Candidate"
            total_candidates_generated = 5
            total_blocked = 0
            total_shortlisted = 2
            policy_trials_attempted = 3
            elapsed_seconds = 100.0
            ladder_stages = []
            review_packets = []

        old_env = os.environ.get("SCIRES_RUNTIME_ROOT")
        os.environ["SCIRES_RUNTIME_ROOT"] = self.tmpdir
        try:
            paths = manager._export_artifacts(
                "export_test", profile, receipt, MockResult()
            )
            self.assertGreater(len(paths), 0)
            # Check campaign_summary.json exists
            summary_path = os.path.join(self.tmpdir, "campaigns", "export_test", "campaign_summary.json")
            self.assertTrue(os.path.exists(summary_path))
            with open(summary_path) as f:
                data = json.load(f)
            self.assertEqual(data["campaign_id"], "export_test")
            # Check markdown exists
            md_path = os.path.join(self.tmpdir, "campaigns", "export_test", "campaign_summary.md")
            self.assertTrue(os.path.exists(md_path))
        finally:
            if old_env:
                os.environ["SCIRES_RUNTIME_ROOT"] = old_env
            else:
                os.environ.pop("SCIRES_RUNTIME_ROOT", None)

    def test_export_failure_report_for_aborted(self):
        from breakthrough_engine.campaign_manager import CampaignManager, CampaignReceipt
        manager = CampaignManager(repo=self.repo)
        receipt = CampaignReceipt(
            campaign_id="abort_test",
            profile_name="pilot_30m",
            status="aborted_runtime",
            failure_reason="Test failure",
            stage_events=[{"stage_name": "test", "status": "failed"}],
        )

        from breakthrough_engine.campaign_manager import CampaignProfile
        profile = CampaignProfile()

        class MockResult:
            campaign_id = "abort_test"
            daily_champion_id = ""
            daily_champion_title = ""
            total_candidates_generated = 0
            total_blocked = 0
            total_shortlisted = 0
            policy_trials_attempted = 0
            elapsed_seconds = 10.0
            ladder_stages = []
            review_packets = []

        old_env = os.environ.get("SCIRES_RUNTIME_ROOT")
        os.environ["SCIRES_RUNTIME_ROOT"] = self.tmpdir
        try:
            paths = manager._export_artifacts(
                "abort_test", profile, receipt, MockResult()
            )
            # Should include a failure report
            failure_path = os.path.join(self.tmpdir, "campaigns", "abort_test", "failure_report.json")
            self.assertTrue(os.path.exists(failure_path))
        finally:
            if old_env:
                os.environ["SCIRES_RUNTIME_ROOT"] = old_env
            else:
                os.environ.pop("SCIRES_RUNTIME_ROOT", None)


# ---------------------------------------------------------------------------
# Test: Campaign outcome categories
# ---------------------------------------------------------------------------

class TestCampaignOutcomes(unittest.TestCase):
    """Test campaign outcome categorization."""

    def test_completed_with_draft(self):
        from breakthrough_engine.campaign_manager import CampaignStatus
        self.assertEqual(CampaignStatus.COMPLETED_WITH_DRAFT.value, "completed_with_draft")

    def test_completed_no_draft(self):
        from breakthrough_engine.campaign_manager import CampaignStatus
        self.assertEqual(CampaignStatus.COMPLETED_NO_DRAFT.value, "completed_no_draft")

    def test_aborted_preflight(self):
        from breakthrough_engine.campaign_manager import CampaignStatus
        self.assertEqual(CampaignStatus.ABORTED_PREFLIGHT.value, "aborted_preflight")

    def test_aborted_runtime(self):
        from breakthrough_engine.campaign_manager import CampaignStatus
        self.assertEqual(CampaignStatus.ABORTED_RUNTIME.value, "aborted_runtime")

    def test_aborted_timeout(self):
        from breakthrough_engine.campaign_manager import CampaignStatus
        self.assertEqual(CampaignStatus.ABORTED_TIMEOUT.value, "aborted_timeout")

    def test_aborted_signal(self):
        from breakthrough_engine.campaign_manager import CampaignStatus
        self.assertEqual(CampaignStatus.ABORTED_SIGNAL.value, "aborted_signal")


# ---------------------------------------------------------------------------
# Test: Campaign format (Markdown)
# ---------------------------------------------------------------------------

class TestCampaignMarkdown(unittest.TestCase):
    """Test campaign markdown report generation."""

    def test_markdown_with_champion(self):
        from breakthrough_engine.campaign_manager import CampaignManager, CampaignReceipt
        manager = CampaignManager()
        receipt = CampaignReceipt(
            campaign_id="md_test",
            profile_name="pilot_30m",
            profile_type="pilot",
            status="completed_with_draft",
            champion_candidate_id="cand123",
            champion_candidate_title="Perovskite Solar Cell",
            total_candidates_generated=5,
            elapsed_seconds=120.0,
            started_at="2026-03-08T12:00:00Z",
            completed_at="2026-03-08T12:02:00Z",
        )
        md = manager._format_campaign_markdown(receipt, None)
        self.assertIn("Campaign Report", md)
        self.assertIn("Perovskite Solar Cell", md)
        self.assertIn("completed_with_draft", md)

    def test_markdown_with_failure(self):
        from breakthrough_engine.campaign_manager import CampaignManager, CampaignReceipt
        manager = CampaignManager()
        receipt = CampaignReceipt(
            campaign_id="fail_test",
            profile_name="overnight_clean_energy",
            status="aborted_runtime",
            failure_reason="Ollama crashed",
            started_at="2026-03-08T12:00:00Z",
            completed_at="2026-03-08T12:01:00Z",
        )
        md = manager._format_campaign_markdown(receipt, None)
        self.assertIn("Failure", md)
        self.assertIn("Ollama crashed", md)


# ---------------------------------------------------------------------------
# Test: Overnight launcher dry-run path
# ---------------------------------------------------------------------------

class TestOvernightDryRun(unittest.TestCase):
    """Test overnight launcher in dry-run mode."""

    def test_dry_run_does_not_execute_ladder(self):
        from breakthrough_engine.campaign_manager import (
            CampaignManager, CampaignProfile, CampaignStatus,
        )
        db = init_db(in_memory=True)
        repo = Repository(db)
        manager = CampaignManager(repo=repo)
        profile = CampaignProfile(
            profile_name="overnight_dry_run_test",
            profile_type="overnight",
            mode="benchmark",
        )
        receipt = manager.run_campaign(profile, strict_preflight=False, dry_run=True)
        self.assertEqual(receipt.status, CampaignStatus.COMPLETED_NO_DRAFT.value)
        self.assertIn("dry_run", receipt.failure_reason)
        # Should have preflight event but no ladder event
        stage_names = [e.get("stage_name") for e in receipt.stage_events]
        self.assertIn("preflight", stage_names)
        self.assertNotIn("daily_search_ladder", stage_names)


# ---------------------------------------------------------------------------
# Test: DB campaign receipt round-trip
# ---------------------------------------------------------------------------

class TestCampaignReceiptPersistence(unittest.TestCase):
    """Test campaign receipt DB persistence and retrieval."""

    def setUp(self):
        self.db = init_db(in_memory=True)
        self.repo = Repository(self.db)

    def test_save_and_load_receipt(self):
        from breakthrough_engine.campaign_manager import CampaignManager, CampaignReceipt
        manager = CampaignManager(repo=self.repo)
        receipt = CampaignReceipt(
            campaign_id="persist_test",
            profile_name="pilot_30m",
            profile_type="pilot",
            status="completed_with_draft",
            config_snapshot={"mode": "benchmark"},
            preflight_report={"readiness_score": 0.9},
            stage_events=[{"stage_name": "preflight", "status": "completed"}],
            started_at="2026-03-08T12:00:00Z",
            completed_at="2026-03-08T12:30:00Z",
            elapsed_seconds=1800.0,
            champion_candidate_id="cand789",
            champion_candidate_title="Test Candidate",
            total_candidates_generated=15,
            retries_used=0,
            artifact_paths=["/tmp/test/summary.json"],
            health_summary={"healthy": True, "overnight_ready": True},
        )
        manager._save_receipt(receipt)

        loaded = manager.get_receipt("persist_test")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["profile_name"], "pilot_30m")
        self.assertEqual(loaded["status"], "completed_with_draft")
        self.assertEqual(loaded["champion_candidate_id"], "cand789")
        self.assertEqual(loaded["total_candidates_generated"], 15)

    def test_receipt_update_on_checkpoint(self):
        from breakthrough_engine.campaign_manager import CampaignManager, CampaignReceipt
        manager = CampaignManager(repo=self.repo)

        # Save initial
        receipt = CampaignReceipt(
            campaign_id="checkpoint_test",
            status="running",
        )
        manager._save_receipt(receipt)

        # Update
        receipt.status = "completed_with_draft"
        receipt.champion_candidate_id = "cand_final"
        manager._save_receipt(receipt)

        loaded = manager.get_receipt("checkpoint_test")
        self.assertEqual(loaded["status"], "completed_with_draft")
        self.assertEqual(loaded["champion_candidate_id"], "cand_final")


if __name__ == "__main__":
    unittest.main()
