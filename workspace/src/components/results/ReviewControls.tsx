"use client";

import { useState } from "react";
import type { ReviewState } from "@/lib/types";

const REVIEW_OPTIONS: Array<{
  value: ReviewState;
  label: string;
  color: string;
}> = [
  { value: "awaiting_review", label: "Awaiting Review", color: "var(--accent-amber)" },
  { value: "approved_for_validation", label: "Approved", color: "var(--accent-green)" },
  { value: "rejected_by_operator", label: "Rejected", color: "var(--accent-red)" },
  { value: "needs_more_analysis", label: "Needs Analysis", color: "var(--accent-purple)" },
  { value: "exported", label: "Exported", color: "var(--text-muted)" },
];

export default function ReviewControls({
  briefId,
  currentState,
  currentNotes,
  onUpdated,
}: {
  briefId: string;
  currentState: ReviewState;
  currentNotes?: string;
  onUpdated?: (state: ReviewState, notes: string) => void;
}) {
  const [state, setState] = useState<ReviewState>(currentState);
  const [notes, setNotes] = useState(currentNotes || "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const res = await fetch(`/api/briefs/${briefId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ review_state: state, review_notes: notes }),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
        onUpdated?.(state, notes);
      }
    } catch {
      // Silent failure — user can retry
    } finally {
      setSaving(false);
    }
  };

  const hasChanges = state !== currentState || notes !== (currentNotes || "");

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        {REVIEW_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setState(opt.value)}
            className={`text-[10px] px-2 py-1 rounded border transition-colors ${
              state === opt.value
                ? "bg-opacity-15"
                : "border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
            style={
              state === opt.value
                ? {
                    color: opt.color,
                    borderColor: opt.color,
                    backgroundColor: `color-mix(in srgb, ${opt.color} 10%, transparent)`,
                  }
                : undefined
            }
          >
            {opt.label}
          </button>
        ))}
      </div>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Review notes (optional)..."
        rows={2}
        className="w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50 resize-none"
      />
      <div className="flex items-center gap-2">
        <button
          onClick={handleSave}
          disabled={saving || !hasChanges}
          className="text-[10px] px-3 py-1 rounded bg-[var(--accent-blue)] text-white hover:bg-[var(--accent-blue)]/80 transition-colors disabled:opacity-40"
        >
          {saving ? "Saving..." : saved ? "Saved" : "Save Review"}
        </button>
        {saved && (
          <span className="text-[10px] text-[var(--accent-green)]">Updated</span>
        )}
      </div>
    </div>
  );
}
