"""Tests for the battery review workflow."""

import json

import pytest

from breakthrough_engine.battery_decision_brief import (
    BatteryDecisionBrief,
    save_decision_brief,
)
from breakthrough_engine.battery_review import (
    REVIEW_STATES,
    BriefStore,
    ReviewRecord,
)


@pytest.fixture
def store(tmp_path):
    return BriefStore(briefs_dir=tmp_path)


@pytest.fixture
def sample_brief(tmp_path):
    brief = BatteryDecisionBrief(
        title="Test Brief",
        headline="Test headline",
        final_score=0.72,
        candidate_family="reduced_resistance",
    )
    save_decision_brief(brief, output_dir=str(tmp_path))
    return brief


class TestReviewStates:
    def test_five_states_defined(self):
        assert len(REVIEW_STATES) == 5

    def test_expected_states(self):
        assert "awaiting_review" in REVIEW_STATES
        assert "approved_for_validation" in REVIEW_STATES
        assert "rejected_by_operator" in REVIEW_STATES
        assert "needs_more_analysis" in REVIEW_STATES
        assert "exported" in REVIEW_STATES


class TestReviewRecord:
    def test_create_record(self):
        r = ReviewRecord(brief_id="abc", state="approved_for_validation", notes="LGTM")
        assert r.brief_id == "abc"
        assert r.state == "approved_for_validation"
        assert r.notes == "LGTM"


class TestBriefStore:
    def test_list_briefs_empty(self, store):
        assert store.list_briefs() == []

    def test_list_briefs_finds_saved(self, store, sample_brief):
        briefs = store.list_briefs()
        assert len(briefs) == 1
        assert briefs[0]["id"] == sample_brief.id

    def test_get_brief(self, store, sample_brief):
        brief = store.get_brief(sample_brief.id)
        assert brief is not None
        assert brief["title"] == "Test Brief"

    def test_get_brief_not_found(self, store):
        assert store.get_brief("nonexistent") is None

    def test_update_review_state(self, store, sample_brief):
        record = store.update_review_state(
            sample_brief.id, "approved_for_validation",
            reviewer="operator", notes="Approved for deeper testing",
        )
        assert record is not None
        assert record.state == "approved_for_validation"
        assert record.reviewer == "operator"

        # Verify brief was updated
        brief = store.get_brief(sample_brief.id)
        assert brief["review_state"] == "approved_for_validation"

    def test_invalid_state_raises(self, store, sample_brief):
        with pytest.raises(ValueError, match="Invalid review state"):
            store.update_review_state(sample_brief.id, "invalid_state")

    def test_update_nonexistent_brief(self, store):
        assert store.update_review_state("none", "exported") is None

    def test_list_reviews(self, store, sample_brief):
        store.update_review_state(sample_brief.id, "approved_for_validation")
        store.update_review_state(sample_brief.id, "exported")
        reviews = store.list_reviews()
        assert len(reviews) == 2

    def test_list_reviews_filtered(self, store, sample_brief):
        store.update_review_state(sample_brief.id, "approved_for_validation")
        reviews = store.list_reviews(brief_id=sample_brief.id)
        assert len(reviews) == 1
        assert reviews[0]["brief_id"] == sample_brief.id

    def test_export_brief(self, store, sample_brief, tmp_path):
        export_dir = tmp_path / "exports"
        path = store.export_brief(sample_brief.id, export_dir=export_dir)
        assert path is not None
        assert export_dir.exists()
        exported = json.loads((export_dir / f"brief_{sample_brief.id}_export.json").read_text())
        assert exported["title"] == "Test Brief"

        # Verify state updated to exported
        brief = store.get_brief(sample_brief.id)
        assert brief["review_state"] == "exported"

    def test_export_nonexistent(self, store):
        assert store.export_brief("none") is None

    def test_review_workflow_end_to_end(self, store, sample_brief):
        """Full workflow: awaiting → needs_more → approved → exported."""
        brief = store.get_brief(sample_brief.id)
        assert brief["review_state"] == "awaiting_review"

        store.update_review_state(sample_brief.id, "needs_more_analysis", notes="Check thermal")
        brief = store.get_brief(sample_brief.id)
        assert brief["review_state"] == "needs_more_analysis"

        store.update_review_state(sample_brief.id, "approved_for_validation", notes="Thermal OK")
        brief = store.get_brief(sample_brief.id)
        assert brief["review_state"] == "approved_for_validation"

        store.export_brief(sample_brief.id)
        brief = store.get_brief(sample_brief.id)
        assert brief["review_state"] == "exported"

        reviews = store.list_reviews(brief_id=sample_brief.id)
        assert len(reviews) == 3  # needs_more, approved, exported
