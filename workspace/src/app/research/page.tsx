"use client";

import { useState } from "react";
import { useJobs } from "@/hooks/useJobs";
import { useBriefs } from "@/hooks/useBriefs";
import JobList from "@/components/jobs/JobList";
import type { ResearchBrief } from "@/lib/types";

const EVIDENCE_COLORS: Record<string, string> = {
  strong: "var(--accent-green)",
  moderate: "var(--accent-blue)",
  weak: "var(--accent-amber)",
  insufficient: "var(--accent-red)",
};

const CONFIDENCE_COLORS: Record<string, string> = {
  high: "var(--accent-green)",
  medium: "var(--accent-amber)",
  low: "var(--accent-red)",
};

function ResearchBriefCard({ brief }: { brief: ResearchBrief }) {
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4">
        <div className="flex items-center gap-2 mb-2">
          <span
            className="text-[9px] px-1.5 py-0.5 rounded-full border"
            style={{
              color: "var(--accent-purple)",
              borderColor: "var(--accent-purple)",
            }}
          >
            Research Brief
          </span>
          <span
            className="text-[9px] px-1.5 py-0.5 rounded-full border"
            style={{
              color: EVIDENCE_COLORS[brief.evidence_quality] || "var(--text-muted)",
              borderColor: EVIDENCE_COLORS[brief.evidence_quality] || "var(--border)",
            }}
          >
            Evidence: {brief.evidence_quality}
          </span>
          <span className="text-[9px] text-[var(--text-muted)]">
            {brief.domain}
          </span>
        </div>
        <h3 className="text-sm font-medium text-[var(--text-primary)] leading-tight">
          {brief.headline}
        </h3>
        <p className="text-xs text-[var(--text-secondary)] mt-1.5 leading-snug">
          {brief.summary}
        </p>
        <p className="text-[10px] text-[var(--text-muted)] mt-1">
          Topic: {brief.topic} &middot;{" "}
          {new Date(brief.created_at).toLocaleDateString()}
        </p>
      </div>

      {/* Promising Directions */}
      {brief.promising_directions.length > 0 && (
        <div className="px-5 py-3 border-t border-[var(--border)]">
          <h4 className="text-[10px] font-semibold text-[var(--accent-green)] uppercase tracking-wider mb-2">
            Promising Directions
          </h4>
          <div className="space-y-2.5">
            {brief.promising_directions.map((d, i) => (
              <div key={i}>
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs font-medium text-[var(--text-primary)]">
                    {d.title}
                  </span>
                  <span
                    className="text-[9px] px-1 py-0.5 rounded border"
                    style={{
                      color: CONFIDENCE_COLORS[d.confidence],
                      borderColor: CONFIDENCE_COLORS[d.confidence],
                    }}
                  >
                    {d.confidence}
                  </span>
                </div>
                <p className="text-xs text-[var(--text-secondary)] leading-snug">
                  {d.description}
                </p>
                <p className="text-[10px] text-[var(--text-muted)] mt-0.5 leading-snug">
                  Rationale: {d.rationale}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Rejected Directions */}
      {brief.rejected_directions.length > 0 && (
        <div className="px-5 py-3 border-t border-[var(--border)]">
          <h4 className="text-[10px] font-semibold text-[var(--accent-red)] uppercase tracking-wider mb-2">
            Rejected Directions
          </h4>
          <div className="space-y-2">
            {brief.rejected_directions.map((d, i) => (
              <div key={i}>
                <span className="text-xs font-medium text-[var(--text-primary)]">
                  {d.title}
                </span>
                <p className="text-xs text-[var(--text-secondary)] leading-snug">
                  {d.description}
                </p>
                <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
                  Reason: {d.reason}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommended Next */}
      {brief.recommended_next && (
        <div className="px-5 py-3 border-t border-[var(--border)]">
          <div className="bg-[var(--accent-purple)]/5 border border-[var(--accent-purple)]/20 rounded px-4 py-3">
            <h4 className="text-[10px] font-semibold text-[var(--accent-purple)] uppercase tracking-wider mb-0.5">
              Recommended Next Step
            </h4>
            <p className="text-xs text-[var(--text-primary)] leading-snug">
              {brief.recommended_next}
            </p>
          </div>
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

export default function ResearchPage() {
  const { jobs, submitJob } = useJobs();
  const { briefs, refresh: refreshBriefs } = useBriefs("research");

  const [topic, setTopic] = useState("");
  const [domain, setDomain] = useState("battery");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const researchJobs = jobs.filter((j) => j.product_area === "research");
  const researchBriefs = briefs as unknown as ResearchBrief[];

  const handleSubmit = async () => {
    if (!topic.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      await submitJob("research", { topic: topic.trim(), domain });
      setTopic("");
      // Refresh briefs after a delay to catch completed jobs
      setTimeout(() => refreshBriefs(), 3000);
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
          Research
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Explore new solution directions, generate candidates, and review
          promising paths
        </p>
      </div>

      {/* Research Input */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Research Topic
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 space-y-4">
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1.5">
              Problem or Topic
            </label>
            <textarea
              rows={3}
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Describe the energy problem or research direction to explore..."
              className="w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50 resize-none"
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1.5">
              Domain Focus
            </label>
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-blue)]/50"
            >
              <option value="battery">Battery</option>
              <option value="pv">Photovoltaic</option>
              <option value="general">General Energy</option>
            </select>
          </div>
          {error && (
            <p className="text-xs text-[var(--accent-red)]">{error}</p>
          )}
          <button
            onClick={handleSubmit}
            disabled={submitting || !topic.trim()}
            className="px-4 py-2 bg-[var(--accent-purple)] text-white text-sm rounded hover:bg-[var(--accent-purple)]/80 transition-colors disabled:opacity-50"
          >
            {submitting ? "Starting..." : "Start Research"}
          </button>
        </div>
      </section>

      {/* Active Research Jobs */}
      {researchJobs.some(
        (j) => j.status === "running" || j.status === "queued"
      ) && (
        <section className="mb-8">
          <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Active Jobs
          </h2>
          <JobList
            jobs={researchJobs.filter(
              (j) => j.status === "running" || j.status === "queued"
            )}
          />
        </section>
      )}

      {/* Research Briefs */}
      {researchBriefs.length > 0 ? (
        <>
          <section className="mb-8">
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
              Research Briefs ({researchBriefs.length})
            </h2>
            <div className="space-y-4">
              {researchBriefs.map((brief) => (
                <ResearchBriefCard key={brief.id} brief={brief} />
              ))}
            </div>
          </section>
        </>
      ) : (
        <>
          {/* Placeholder when no briefs exist */}
          <section className="mb-8">
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
              Promising Directions
            </h2>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
              <p className="text-sm text-[var(--text-muted)] text-center">
                Start a research run to discover promising directions.
              </p>
            </div>
          </section>

          <section>
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
              Rejected Directions
            </h2>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
              <p className="text-sm text-[var(--text-muted)] text-center">
                Rejected candidates and failed paths will appear here.
              </p>
            </div>
          </section>
        </>
      )}

      {/* Recent Jobs */}
      {researchJobs.some(
        (j) => j.status === "completed" || j.status === "failed"
      ) && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Job History
          </h2>
          <JobList
            jobs={researchJobs.filter(
              (j) => j.status === "completed" || j.status === "failed"
            )}
          />
        </section>
      )}
    </div>
  );
}
