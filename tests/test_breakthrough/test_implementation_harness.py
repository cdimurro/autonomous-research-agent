"""Tests for the Implementation Safety Harness.

Covers session creation, gate logic, review artifact parsing,
and commit-block enforcement for both pass and fail paths.
"""

import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the harness module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import impl_session as ish


@pytest.fixture
def tmp_session_dir(tmp_path):
    """Redirect session artifacts to a temp directory."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    with patch.object(ish, "SESSION_DIR", session_dir), \
         patch.object(ish, "ACTIVE_SESSION_FILE", session_dir / "active_session.json"), \
         patch.object(ish, "REVIEW_ARTIFACT_FILE", session_dir / "active_review.json"):
        yield session_dir


def _write_session(session_dir, **overrides):
    session = {
        "session_id": "ISH-test1234",
        "branch": "test-branch",
        "execution_mode": "IMPLEMENT",
        "scope": "test scope",
        "files_expected_to_change": [],
        "risk_level": "low",
        "tests_expected_to_run": [],
        "review_gate_required": True,
        "commit_blocked_until_gate_pass": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notes": "",
    }
    session.update(overrides)
    path = session_dir / "active_session.json"
    path.write_text(json.dumps(session, indent=2))
    return session


def _write_review(session_dir, blockers=None, warnings=None, suggestions=None):
    review = {
        "session_id": "ISH-test1234",
        "reviewer": "codex",
        "reviewed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "files_reviewed": [],
        "blockers": blockers or [],
        "warnings": warnings or [],
        "suggestions": suggestions or [],
        "gate_decision": "FAIL" if blockers else "PASS",
        "notes": "",
    }
    path = session_dir / "active_review.json"
    path.write_text(json.dumps(review, indent=2))
    return review


# ── Session artifact creation ─────────────────────────────────────────────

class TestSessionArtifact:
    def test_session_schema_has_required_fields(self):
        template_path = Path(__file__).resolve().parent.parent.parent / "templates" / "implementation_session.json"
        template = json.loads(template_path.read_text())
        required_keys = {
            "session_id", "branch", "execution_mode", "scope",
            "files_expected_to_change", "risk_level", "tests_expected_to_run",
            "review_gate_required", "commit_blocked_until_gate_pass",
            "created_at", "notes",
        }
        assert required_keys.issubset(set(template.keys()))

    def test_session_template_defaults(self):
        template_path = Path(__file__).resolve().parent.parent.parent / "templates" / "implementation_session.json"
        template = json.loads(template_path.read_text())
        assert template["review_gate_required"] is True
        assert template["commit_blocked_until_gate_pass"] is True


# ── Gate logic — fail paths ───────────────────────────────────────────────

class TestGateFail:
    def test_gate_fails_without_session(self, tmp_session_dir):
        """Gate must fail when no session artifact exists."""
        args = argparse.Namespace()
        rc = ish.cmd_gate(args)
        assert rc == 1

    def test_gate_fails_without_review(self, tmp_session_dir):
        """Gate must fail when session exists but review is missing."""
        _write_session(tmp_session_dir)
        args = argparse.Namespace()
        rc = ish.cmd_gate(args)
        assert rc == 1

    def test_gate_fails_with_blockers(self, tmp_session_dir):
        """Gate must fail when review has blockers."""
        _write_session(tmp_session_dir)
        _write_review(tmp_session_dir, blockers=["Missing test for new function"])
        args = argparse.Namespace()
        rc = ish.cmd_gate(args)
        assert rc == 1

    def test_review_status_fails_without_artifact(self, tmp_session_dir):
        args = argparse.Namespace()
        rc = ish.cmd_review_status(args)
        assert rc == 1

    def test_review_status_fails_with_blockers(self, tmp_session_dir):
        _write_review(tmp_session_dir, blockers=["Contract mismatch"])
        args = argparse.Namespace()
        rc = ish.cmd_review_status(args)
        assert rc == 1


# ── Gate logic — pass paths ───────────────────────────────────────────────

class TestGatePass:
    def test_gate_passes_with_clean_review(self, tmp_session_dir):
        """Gate passes when session + review exist and no blockers."""
        _write_session(tmp_session_dir)
        _write_review(tmp_session_dir, blockers=[], warnings=["Minor style issue"])
        args = argparse.Namespace()
        rc = ish.cmd_gate(args)
        assert rc == 0

    def test_gate_passes_when_not_blocked(self, tmp_session_dir):
        """Gate passes when commit_blocked_until_gate_pass is False."""
        _write_session(tmp_session_dir, commit_blocked_until_gate_pass=False)
        # No review artifact — but gate should still pass
        args = argparse.Namespace()
        rc = ish.cmd_gate(args)
        assert rc == 0

    def test_review_status_passes_clean(self, tmp_session_dir):
        _write_review(tmp_session_dir, blockers=[], warnings=[])
        args = argparse.Namespace()
        rc = ish.cmd_review_status(args)
        assert rc == 0


# ── Review artifact format ────────────────────────────────────────────────

class TestReviewArtifact:
    def test_write_review_creates_artifact(self, tmp_session_dir):
        _write_session(tmp_session_dir)
        args = argparse.Namespace(
            files=["a.py"], blockers=None, warnings="Style|Naming",
            suggestions=None, notes="Looks good"
        )
        rc = ish.cmd_write_review(args)
        assert rc == 0
        review = json.loads((tmp_session_dir / "active_review.json").read_text())
        assert review["gate_decision"] == "PASS"
        assert review["blockers"] == []
        assert len(review["warnings"]) == 2

    def test_write_review_with_blockers(self, tmp_session_dir):
        _write_session(tmp_session_dir)
        args = argparse.Namespace(
            files=["a.py"], blockers="Missing test|Contract violation",
            warnings=None, suggestions=None, notes=""
        )
        rc = ish.cmd_write_review(args)
        assert rc == 0
        review = json.loads((tmp_session_dir / "active_review.json").read_text())
        assert review["gate_decision"] == "FAIL"
        assert len(review["blockers"]) == 2


# ── Scope drift detection ────────────────────────────────────────────────

class TestScopeDrift:
    def test_no_drift_when_no_files_declared(self, tmp_session_dir):
        session = {"files_expected_to_change": []}
        issues = ish._check_scope_drift(session)
        assert issues == []

    def test_drift_detected_concept(self):
        """Verify drift logic detects undeclared files (unit-level)."""
        # This tests the logic path, not actual git state
        session = {"files_expected_to_change": ["a.py"]}
        # Mock git to return a changed file not in scope
        with patch("subprocess.check_output") as mock_git:
            mock_git.side_effect = [
                "a.py\nb.py\n",  # diff HEAD
                "",               # cached
                "",               # untracked
            ]
            issues = ish._check_scope_drift(session)
            assert len(issues) == 1
            assert "b.py" in issues[0]


# ── End-to-end simulations ────────────────────────────────────────────────

class TestEndToEnd:
    def test_happy_path(self, tmp_session_dir):
        """Session init → clean review → gate pass."""
        _write_session(tmp_session_dir)
        _write_review(tmp_session_dir, blockers=[], warnings=["Minor"])
        rc = ish.cmd_gate(argparse.Namespace())
        assert rc == 0

    def test_fail_then_fix_path(self, tmp_session_dir):
        """Session init → blocker → fix → gate pass."""
        _write_session(tmp_session_dir)

        # First review: blocker
        _write_review(tmp_session_dir, blockers=["Missing wiring"])
        rc = ish.cmd_gate(argparse.Namespace())
        assert rc == 1

        # Fix: rewrite review without blockers
        _write_review(tmp_session_dir, blockers=[], warnings=["Fixed wiring"])
        rc = ish.cmd_gate(argparse.Namespace())
        assert rc == 0

    def test_clean_archives_artifacts(self, tmp_session_dir):
        _write_session(tmp_session_dir)
        _write_review(tmp_session_dir)
        rc = ish.cmd_clean(argparse.Namespace())
        assert rc == 0
        assert not (tmp_session_dir / "active_session.json").exists()
        assert not (tmp_session_dir / "active_review.json").exists()
        assert (tmp_session_dir / "archive").exists()


# Need argparse for Namespace
import argparse
