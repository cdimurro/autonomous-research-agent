"use client";

import { useState } from "react";
import ConfidenceBadge from "./ConfidenceBadge";
import SidecarBadge from "./SidecarBadge";
import ScoreBar from "./ScoreBar";

interface BriefData {
  id: string;
  title: string;
  headline: string;
  candidate_family: string;
  chemistry?: string | null;
  final_score: number;
  score_components: Record<string, number>;
  score_summary: string;
  why_promising: string;
  fast_charge_summary: string;
  fast_charge_retention?: number | null;
  resistance_growth_pct?: number | null;
  degradation_summary: string;
  worst_stress_retention?: number | null;
  cathode_thermal_retention?: number | null;
  sidecar_status: string;
  sidecar_gate_decision: string;
  sidecar_concordance?: number | null;
  sidecar_summary?: string;
  sidecar_what_it_means?: string;
  sidecar_calibration_note?: string;
  caveats: string[];
  confidence_tier: string;
  review_state: string;
  recommended_action?: string;
  vs_alternatives?: string;
  created_at: string;
  benchmark_seed?: number | null;
  parameters?: Record<string, unknown>;
  baseline_metrics?: Record<string, unknown>;
  candidate_metrics?: Record<string, unknown>;
  [key: string]: unknown;
}

const REVIEW_LABELS: Record<string, { color: string; label: string }> = {
  awaiting_review: { color: "var(--accent-amber)", label: "Awaiting Review" },
  approved_for_validation: {
    color: "var(--accent-green)",
    label: "Approved",
  },
  rejected_by_operator: { color: "var(--accent-red)", label: "Rejected" },
  needs_more_analysis: {
    color: "var(--accent-purple)",
    label: "Needs Analysis",
  },
  exported: { color: "var(--text-muted)", label: "Exported" },
};

function formatPercent(val: number | null | undefined): string {
  if (val === null || val === undefined) return "N/A";
  return `${(val * 100).toFixed(1)}%`;
}

export default function DecisionBriefCard({
  brief,
  defaultExpanded = false,
}: {
  brief: BriefData;
  defaultExpanded?: boolean;
}) {
  const [showTechnical, setShowTechnical] = useState(false);
  const [expanded, setExpanded] = useState(defaultExpanded);
  const reviewStyle = REVIEW_LABELS[brief.review_state] ?? REVIEW_LABELS.awaiting_review;

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-5 py-4 flex items-start justify-between gap-4 hover:bg-[var(--bg-hover)] transition-colors"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <ConfidenceBadge tier={brief.confidence_tier} />
            <SidecarBadge decision={brief.sidecar_gate_decision} />
            <span
              className="text-[10px] px-2 py-0.5 rounded-full border"
              style={{
                color: reviewStyle.color,
                borderColor: reviewStyle.color,
              }}
            >
              {reviewStyle.label}
            </span>
          </div>
          <h3 className="text-sm font-medium text-[var(--text-primary)] mt-2">
            {brief.title || brief.headline}
          </h3>
          <p className="text-xs text-[var(--text-secondary)] mt-1 line-clamp-2">
            {brief.headline}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-2xl font-bold text-[var(--text-primary)] font-mono">
            {brief.final_score.toFixed(3)}
          </div>
          <p className="text-[10px] text-[var(--text-muted)]">
            {brief.candidate_family}
          </p>
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-[var(--border)]">
          {/* Human-facing summary */}
          <div className="px-5 py-4 space-y-5">
            {/* Why Promising */}
            {brief.why_promising && (
              <div>
                <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5">
                  Why Promising
                </h4>
                <p className="text-sm text-[var(--text-secondary)]">
                  {brief.why_promising}
                </p>
              </div>
            )}

            {/* Key Metrics */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
                  Fast-Charge
                </h4>
                <p className="text-sm text-[var(--text-secondary)] mb-2">
                  {brief.fast_charge_summary || "No fast-charge data"}
                </p>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">Retention</span>
                    <span className="text-[var(--text-primary)] font-mono">
                      {formatPercent(brief.fast_charge_retention)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">
                      R Growth
                    </span>
                    <span className="text-[var(--text-primary)] font-mono">
                      {brief.resistance_growth_pct !== null &&
                      brief.resistance_growth_pct !== undefined
                        ? `${brief.resistance_growth_pct.toFixed(1)}%`
                        : "N/A"}
                    </span>
                  </div>
                </div>
              </div>
              <div>
                <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
                  Degradation
                </h4>
                <p className="text-sm text-[var(--text-secondary)] mb-2">
                  {brief.degradation_summary || "No degradation data"}
                </p>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">
                      Worst Stress
                    </span>
                    <span className="text-[var(--text-primary)] font-mono">
                      {formatPercent(brief.worst_stress_retention)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">
                      Cathode Thermal
                    </span>
                    <span className="text-[var(--text-primary)] font-mono">
                      {formatPercent(brief.cathode_thermal_retention)}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Sidecar */}
            {brief.sidecar_what_it_means && (
              <div>
                <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5">
                  Sidecar Verification
                </h4>
                <p className="text-sm text-[var(--text-secondary)]">
                  {brief.sidecar_what_it_means}
                </p>
                {brief.sidecar_concordance !== null &&
                  brief.sidecar_concordance !== undefined && (
                    <p className="text-xs text-[var(--text-muted)] mt-1">
                      Concordance: {brief.sidecar_concordance.toFixed(3)}
                      {brief.sidecar_calibration_note &&
                        ` \u2014 ${brief.sidecar_calibration_note}`}
                    </p>
                  )}
              </div>
            )}

            {/* Caveats */}
            {brief.caveats.length > 0 && (
              <div>
                <h4 className="text-[10px] font-semibold text-[var(--accent-amber)] uppercase tracking-wider mb-1.5">
                  Caveats
                </h4>
                <ul className="space-y-1">
                  {brief.caveats.map((c, i) => (
                    <li
                      key={i}
                      className="text-xs text-[var(--text-secondary)] flex items-start gap-2"
                    >
                      <span className="text-[var(--accent-amber)] mt-0.5 shrink-0">
                        !
                      </span>
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Recommended Next Action */}
            {brief.recommended_action && (
              <div className="bg-[var(--accent-blue)]/5 border border-[var(--accent-blue)]/20 rounded-lg px-4 py-3">
                <h4 className="text-[10px] font-semibold text-[var(--accent-blue)] uppercase tracking-wider mb-1">
                  Recommended Next Step
                </h4>
                <p className="text-sm text-[var(--text-primary)]">
                  {brief.recommended_action}
                </p>
              </div>
            )}

            {/* vs Alternatives */}
            {brief.vs_alternatives && (
              <div>
                <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5">
                  vs. Alternatives
                </h4>
                <p className="text-sm text-[var(--text-secondary)]">
                  {brief.vs_alternatives}
                </p>
              </div>
            )}
          </div>

          {/* Technical Details Toggle */}
          <div className="border-t border-[var(--border)]">
            <button
              onClick={() => setShowTechnical(!showTechnical)}
              className="w-full px-5 py-2.5 text-left text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider hover:bg-[var(--bg-hover)] transition-colors"
            >
              {showTechnical
                ? "Hide Technical Details"
                : "Show Technical Details"}
            </button>
            {showTechnical && (
              <div className="px-5 py-4 space-y-4 bg-[var(--bg-primary)]">
                {/* Score Components */}
                <div>
                  <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
                    Score Components
                  </h4>
                  <div className="space-y-2">
                    {Object.entries(brief.score_components).map(
                      ([name, value]) => (
                        <ScoreBar
                          key={name}
                          label={name.replace(/_/g, " ")}
                          value={Number(value)}
                        />
                      )
                    )}
                  </div>
                </div>

                {/* Parameters */}
                {brief.parameters &&
                  Object.keys(brief.parameters).length > 0 && (
                    <div>
                      <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
                        Candidate Parameters
                      </h4>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                        {Object.entries(brief.parameters).map(([k, v]) => (
                          <div key={k} className="flex justify-between text-xs">
                            <span className="text-[var(--text-muted)]">{k}</span>
                            <span className="text-[var(--text-primary)] font-mono">
                              {typeof v === "number" ? v.toFixed(4) : String(v)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                {/* Meta */}
                <div className="text-xs text-[var(--text-muted)] space-y-0.5">
                  <p>Brief ID: {brief.id}</p>
                  <p>Created: {new Date(brief.created_at).toLocaleString()}</p>
                  {brief.benchmark_seed !== null &&
                    brief.benchmark_seed !== undefined && (
                      <p>Seed: {brief.benchmark_seed}</p>
                    )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
