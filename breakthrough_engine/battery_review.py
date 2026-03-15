"""Minimal human review workflow for battery decision briefs.

Review states:
    awaiting_review         — newly generated, not yet reviewed
    approved_for_validation — operator approves for deeper validation
    rejected_by_operator    — operator rejects
    needs_more_analysis     — operator requests more analysis
    exported                — brief has been exported for external use

Persistence: JSON files in runtime/battery_briefs/ (same dir as briefs).
Review decisions stored alongside briefs as review records.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .domain_models import new_id

REVIEW_STATES = [
    "awaiting_review",
    "approved_for_validation",
    "rejected_by_operator",
    "needs_more_analysis",
    "exported",
]

DEFAULT_BRIEFS_DIR = Path("runtime/battery_briefs")


class ReviewRecord(BaseModel):
    """A single review decision on a battery decision brief."""
    id: str = Field(default_factory=new_id)
    brief_id: str
    state: str  # one of REVIEW_STATES
    reviewer: str = ""
    notes: str = ""
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class BriefStore:
    """File-based store for battery decision briefs and review records.

    Layout:
        briefs_dir/
            brief_{id}.json          — decision brief
            review_{id}.json         — review records (one per review)
    """

    def __init__(self, briefs_dir: Optional[Path] = None):
        self.briefs_dir = briefs_dir or DEFAULT_BRIEFS_DIR
        self.briefs_dir.mkdir(parents=True, exist_ok=True)

    def list_briefs(self) -> list[dict]:
        """List all decision briefs, sorted by created_at descending."""
        briefs = []
        for f in sorted(self.briefs_dir.glob("brief_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                briefs.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return briefs

    def get_brief(self, brief_id: str) -> Optional[dict]:
        """Get a single brief by ID."""
        path = self.briefs_dir / f"brief_{brief_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def update_review_state(
        self, brief_id: str, state: str, reviewer: str = "", notes: str = "",
    ) -> Optional[ReviewRecord]:
        """Set review state on a brief and save review record."""
        if state not in REVIEW_STATES:
            raise ValueError(f"Invalid review state: {state}. Must be one of {REVIEW_STATES}")

        brief_path = self.briefs_dir / f"brief_{brief_id}.json"
        if not brief_path.exists():
            return None

        # Update brief's review_state
        brief = json.loads(brief_path.read_text())
        brief["review_state"] = state
        brief_path.write_text(json.dumps(brief, indent=2, default=str))

        # Save review record
        record = ReviewRecord(
            brief_id=brief_id,
            state=state,
            reviewer=reviewer,
            notes=notes,
        )
        record_path = self.briefs_dir / f"review_{record.id}.json"
        record_path.write_text(json.dumps(record.model_dump(), indent=2, default=str))

        return record

    def list_reviews(self, brief_id: Optional[str] = None) -> list[dict]:
        """List review records, optionally filtered by brief_id."""
        reviews = []
        for f in sorted(self.briefs_dir.glob("review_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                if brief_id and data.get("brief_id") != brief_id:
                    continue
                reviews.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return reviews

    def export_brief(self, brief_id: str, export_dir: Optional[Path] = None) -> Optional[str]:
        """Export a brief to the export directory and mark as exported."""
        brief = self.get_brief(brief_id)
        if not brief:
            return None
        export_path = Path(export_dir or "runtime/battery_exports")
        export_path.mkdir(parents=True, exist_ok=True)
        out = export_path / f"brief_{brief_id}_export.json"
        out.write_text(json.dumps(brief, indent=2, default=str))
        self.update_review_state(brief_id, "exported", notes="Auto-exported")
        return str(out)
