"use client";

import { useState, useEffect } from "react";
import { useJobs } from "@/hooks/useJobs";
import { useBriefs } from "@/hooks/useBriefs";
import JobList from "@/components/jobs/JobList";
import ReviewControls from "@/components/results/ReviewControls";
import ExportButton from "@/components/results/ExportButton";
import ProvenancePanel from "@/components/results/ProvenancePanel";
import type { DiligenceBrief } from "@/lib/types";

const REVIEW_LABELS: Record<string, { color: string; label: string }> = {
  awaiting_review: { color: "var(--accent-amber)", label: "Awaiting Review" },
  approved_for_validation: { color: "var(--accent-green)", label: "Approved" },
  rejected_by_operator: { color: "var(--accent-red)", label: "Rejected" },
  needs_more_analysis: { color: "var(--accent-purple)", label: "Needs Analysis" },
  exported: { color: "var(--text-muted)", label: "Exported" },
};

const SIGNAL_STYLES: Record<string, { color: string; label: string }> = {
  positive: { color: "var(--accent-green)", label: "Positive" },
  negative: { color: "var(--accent-red)", label: "Negative" },
  neutral: { color: "var(--text-muted)", label: "Neutral" },
};

const SEVERITY_STYLES: Record<string, { color: string }> = {
  high: { color: "var(--accent-red)" },
  medium: { color: "var(--accent-amber)" },
  low: { color: "var(--text-muted)" },
};

const FOCUS_OPTIONS = [
  "Technical Validation",
  "Market Assessment",
  "Risk Analysis",
  "Competitive Landscape",
];

function DiligenceBriefCard({ brief, onReviewUpdated }: { brief: DiligenceBrief; onReviewUpdated?: () => void }) {
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [showReview, setShowReview] = useState(false);
  const reviewStyle = REVIEW_LABELS[brief.review_state] ?? REVIEW_LABELS.awaiting_review;

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4">
        <div className="flex items-center gap-2 mb-2">
          <span
            className="text-[9px] px-1.5 py-0.5 rounded-full border"
            style={{
              color: "var(--accent-amber)",
              borderColor: "var(--accent-amber)",
            }}
          >
            Diligence Brief
          </span>
          {brief.focus_areas.map((fa) => (
            <span
              key={fa}
              className="text-[9px] px-1.5 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-muted)]"
            >
              {fa}
            </span>
          ))}
          <span
            className="text-[9px] px-1.5 py-0.5 rounded-full border"
            style={{ color: reviewStyle.color, borderColor: reviewStyle.color }}
          >
            {reviewStyle.label}
          </span>
        </div>
        <h3 className="text-sm font-medium text-[var(--text-primary)] leading-tight">
          {brief.headline}
        </h3>
        <p className="text-xs text-[var(--text-secondary)] mt-1.5 leading-snug">
          {brief.summary}
        </p>
        <div className="flex items-center gap-2 mt-1.5">
          <p className="text-[10px] text-[var(--text-muted)]">
            Subject: {brief.subject} &middot;{" "}
            {new Date(brief.created_at).toLocaleDateString()}
          </p>
          <ExportButton briefId={brief.id} />
        </div>
      </div>

      {/* Provenance */}
      <div className="px-5 py-3 border-t border-[var(--border)]">
        <ProvenancePanel
          briefType="diligence"
          groundingSources={brief.grounding_sources}
          confidenceNote={brief.confidence_note}
        />
      </div>

      {/* Strongest Signals */}
      {brief.strongest_signals.length > 0 && (
        <div className="px-5 py-3 border-t border-[var(--border)]">
          <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
            Key Signals
          </h4>
          <div className="space-y-2.5">
            {brief.strongest_signals.map((s, i) => {
              const style = SIGNAL_STYLES[s.signal_type] || SIGNAL_STYLES.neutral;
              return (
                <div key={i}>
                  <div className="flex items-center gap-2 mb-0.5">
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ background: style.color }}
                    />
                    <span className="text-xs font-medium text-[var(--text-primary)]">
                      {s.title}
                    </span>
                    <span
                      className="text-[9px]"
                      style={{ color: style.color }}
                    >
                      {style.label}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)] leading-snug ml-3.5">
                    {s.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Risks */}
      {brief.risks.length > 0 && (
        <div className="px-5 py-3 border-t border-[var(--border)]">
          <h4 className="text-[10px] font-semibold text-[var(--accent-red)] uppercase tracking-wider mb-2">
            Risks
          </h4>
          <div className="space-y-2">
            {brief.risks.map((r, i) => {
              const sev = SEVERITY_STYLES[r.severity] || SEVERITY_STYLES.medium;
              return (
                <div key={i}>
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-medium text-[var(--text-primary)]">
                      {r.title}
                    </span>
                    <span
                      className="text-[9px] px-1 py-0.5 rounded border"
                      style={{ color: sev.color, borderColor: sev.color }}
                    >
                      {r.severity}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)] leading-snug">
                    {r.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Open Questions */}
      {brief.open_questions.length > 0 && (
        <div className="px-5 py-3 border-t border-[var(--border)]">
          <h4 className="text-[10px] font-semibold text-[var(--accent-blue)] uppercase tracking-wider mb-1.5">
            Open Questions
          </h4>
          <ul className="space-y-0.5">
            {brief.open_questions.map((q, i) => (
              <li
                key={i}
                className="text-xs text-[var(--text-secondary)] flex items-start gap-1.5 leading-snug"
              >
                <span className="text-[var(--accent-blue)] shrink-0">?</span>
                {q}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Recommendation */}
      {brief.recommendation && (
        <div className="px-5 py-3 border-t border-[var(--border)]">
          <div className="bg-[var(--accent-amber)]/5 border border-[var(--accent-amber)]/20 rounded px-4 py-3">
            <h4 className="text-[10px] font-semibold text-[var(--accent-amber)] uppercase tracking-wider mb-0.5">
              Recommendation
            </h4>
            <p className="text-xs text-[var(--text-primary)] leading-snug">
              {brief.recommendation}
            </p>
          </div>
          {brief.confidence_note && (
            <p className="text-[10px] text-[var(--text-muted)] mt-2 leading-snug">
              {brief.confidence_note}
            </p>
          )}
        </div>
      )}

      {/* Caveats */}
      {brief.caveats.length > 0 && (
        <div className="px-5 py-3 border-t border-[var(--border)]">
          <h4 className="text-[10px] font-semibold text-[var(--accent-amber)] uppercase tracking-wider mb-1">
            Caveats
          </h4>
          <ul className="space-y-0.5">
            {brief.caveats.map((c, i) => (
              <li
                key={i}
                className="text-xs text-[var(--text-secondary)] flex items-start gap-1.5 leading-snug"
              >
                <span className="text-[var(--accent-amber)] shrink-0">!</span>
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Review Controls */}
      <div className="border-t border-[var(--border)]">
        <button
          onClick={() => setShowReview(!showReview)}
          className="w-full px-5 py-2 text-left text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider hover:bg-[var(--bg-hover)] transition-colors"
        >
          {showReview ? "Hide Review" : "Review"}
        </button>
        {showReview && (
          <div className="px-5 py-3">
            <ReviewControls
              briefId={brief.id}
              currentState={brief.review_state || "awaiting_review"}
              currentNotes={brief.review_notes}
              onUpdated={() => onReviewUpdated?.()}
            />
          </div>
        )}
      </div>

      {/* Diagnostics Toggle */}
      <div className="border-t border-[var(--border)]">
        <button
          onClick={() => setShowDiagnostics(!showDiagnostics)}
          className="w-full px-5 py-2 text-left text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider hover:bg-[var(--bg-hover)] transition-colors"
        >
          {showDiagnostics ? "Hide Diagnostics" : "Show Diagnostics"}
        </button>
        {showDiagnostics && (
          <div className="px-5 py-4 bg-[var(--bg-primary)] space-y-3">
            {brief.grounding_sources.length > 0 && (
              <div>
                <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1">
                  Grounding Sources
                </h4>
                <ul className="space-y-0.5">
                  {brief.grounding_sources.map((s, i) => (
                    <li key={i} className="text-xs text-[var(--text-secondary)]">
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1">
                Raw Analysis
              </h4>
              <pre className="text-[10px] text-[var(--text-secondary)] whitespace-pre-wrap font-mono leading-relaxed max-h-64 overflow-y-auto">
                {brief.raw_analysis}
              </pre>
            </div>
            <div className="text-[10px] text-[var(--text-muted)] space-y-0.5">
              <p>Brief ID: {brief.id}</p>
              <p>Created: {new Date(brief.created_at).toLocaleString()}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function DiligencePage() {
  const { jobs, submitJob, recentCompletions, clearCompletions } = useJobs();
  const { briefs, refresh: refreshBriefs } = useBriefs("diligence");

  const [subject, setSubject] = useState("");
  const [focusAreas, setFocusAreas] = useState<string[]>([]);
  const [additionalContext, setAdditionalContext] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const diligenceJobs = jobs.filter((j) => j.product_area === "diligence");
  const diligenceBriefs = briefs as unknown as DiligenceBrief[];

  // Auto-refresh briefs when diligence jobs complete
  useEffect(() => {
    const diligenceCompletions = recentCompletions.filter((id) =>
      diligenceJobs.some((j) => j.id === id)
    );
    if (diligenceCompletions.length > 0) {
      refreshBriefs();
      clearCompletions();
    }
  }, [recentCompletions, diligenceJobs, refreshBriefs, clearCompletions]);

  const toggleFocus = (focus: string) => {
    setFocusAreas((prev) =>
      prev.includes(focus) ? prev.filter((f) => f !== focus) : [...prev, focus]
    );
  };

  const handleSubmit = async () => {
    if (!subject.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      await submitJob("diligence", {
        subject: subject.trim(),
        focus_areas: focusAreas,
        additional_context: additionalContext.trim() || undefined,
      });
      setSubject("");
      setFocusAreas([]);
      setAdditionalContext("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="p-8 max-w-5xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-xl font-bold text-[var(--text-primary)]">
          Due Diligence
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Assess companies, technologies, and market opportunities with
          simulation-backed analysis
        </p>
      </div>

      {/* Diligence Input */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Assessment Scope
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 space-y-4">
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1.5">
              Company or Technology
            </label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Company name, technology, or market area..."
              className="w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50"
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1.5">
              Analysis Focus
            </label>
            <div className="flex flex-wrap gap-2">
              {FOCUS_OPTIONS.map((focus) => (
                <button
                  key={focus}
                  onClick={() => toggleFocus(focus)}
                  className={`text-xs px-2.5 py-1.5 rounded border transition-colors ${
                    focusAreas.includes(focus)
                      ? "border-[var(--accent-amber)]/60 bg-[var(--accent-amber)]/10 text-[var(--accent-amber)]"
                      : "border-[var(--border)] bg-[var(--bg-primary)] text-[var(--text-secondary)] hover:border-[var(--accent-amber)]/40"
                  }`}
                >
                  {focus}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1.5">
              Additional Context
            </label>
            <textarea
              rows={3}
              value={additionalContext}
              onChange={(e) => setAdditionalContext(e.target.value)}
              placeholder="Any additional context, constraints, or specific questions..."
              className="w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50 resize-none"
            />
          </div>
          {error && (
            <p className="text-xs text-[var(--accent-red)]">{error}</p>
          )}
          <button
            onClick={handleSubmit}
            disabled={submitting || !subject.trim()}
            className="px-4 py-2 bg-[var(--accent-amber)] text-black text-sm font-medium rounded hover:bg-[var(--accent-amber)]/80 transition-colors disabled:opacity-50"
          >
            {submitting ? "Starting..." : "Run Due Diligence"}
          </button>
        </div>
      </section>

      {/* Active Jobs */}
      {diligenceJobs.some(
        (j) => j.status === "running" || j.status === "queued"
      ) && (
        <section className="mb-8">
          <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Active Jobs
          </h2>
          <JobList
            jobs={diligenceJobs.filter(
              (j) => j.status === "running" || j.status === "queued"
            )}
          />
        </section>
      )}

      {/* Diligence Briefs */}
      {diligenceBriefs.length > 0 ? (
        <section className="mb-8">
          <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Diligence Briefs ({diligenceBriefs.length})
          </h2>
          <div className="space-y-4">
            {diligenceBriefs.map((brief) => (
              <DiligenceBriefCard key={brief.id} brief={brief} onReviewUpdated={() => refreshBriefs()} />
            ))}
          </div>
        </section>
      ) : (
        <>
          <section className="mb-8">
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
              Key Signals
            </h2>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
              <p className="text-sm text-[var(--text-muted)] text-center">
                Run a diligence assessment to see key signals here.
              </p>
            </div>
          </section>

          <section>
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
              Risks &amp; Open Questions
            </h2>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
              <p className="text-sm text-[var(--text-muted)] text-center">
                Identified risks and open questions will appear here.
              </p>
            </div>
          </section>
        </>
      )}

      {/* Job History */}
      {diligenceJobs.some(
        (j) => j.status === "completed" || j.status === "failed"
      ) && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Job History
          </h2>
          <JobList
            jobs={diligenceJobs.filter(
              (j) => j.status === "completed" || j.status === "failed"
            )}
          />
        </section>
      )}
    </div>
  );
}
