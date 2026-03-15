"use client";

import { useState } from "react";

interface ResultData {
  title: string;
  type: string;
  domain: string;
  created_at: string;
  summary?: string | null;
  recommendation?: string | null;
  confidence?: string | null;
  tradeoffs?: string[] | null;
  caveats?: string[] | null;
  next_step?: string | null;
  data: Record<string, unknown>;
}

export default function ResultSummaryCard({ result }: { result: ResultData }) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--bg-hover)] text-[var(--text-muted)]">
            {result.type.replace(/_/g, " ")}
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--bg-hover)] text-[var(--text-muted)]">
            {result.domain}
          </span>
        </div>
        <h3 className="text-sm font-medium text-[var(--text-primary)] mt-2">
          {result.title}
        </h3>
        {result.summary && (
          <p className="text-xs text-[var(--text-secondary)] mt-1">
            {result.summary}
          </p>
        )}
      </div>

      {/* Key Answers */}
      <div className="px-5 pb-4 space-y-3">
        {result.recommendation && (
          <div>
            <h4 className="text-[10px] font-semibold text-[var(--accent-green)] uppercase tracking-wider mb-1">
              Recommendation
            </h4>
            <p className="text-sm text-[var(--text-primary)]">
              {result.recommendation}
            </p>
          </div>
        )}

        {result.tradeoffs && result.tradeoffs.length > 0 && (
          <div>
            <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1">
              Tradeoffs
            </h4>
            <ul className="space-y-0.5">
              {result.tradeoffs.map((t, i) => (
                <li key={i} className="text-xs text-[var(--text-secondary)]">
                  &mdash; {t}
                </li>
              ))}
            </ul>
          </div>
        )}

        {result.caveats && result.caveats.length > 0 && (
          <div>
            <h4 className="text-[10px] font-semibold text-[var(--accent-amber)] uppercase tracking-wider mb-1">
              Caveats
            </h4>
            <ul className="space-y-0.5">
              {result.caveats.map((c, i) => (
                <li key={i} className="text-xs text-[var(--text-secondary)]">
                  ! {c}
                </li>
              ))}
            </ul>
          </div>
        )}

        {result.next_step && (
          <div className="bg-[var(--accent-blue)]/5 border border-[var(--accent-blue)]/20 rounded-lg px-3 py-2">
            <h4 className="text-[10px] font-semibold text-[var(--accent-blue)] uppercase tracking-wider mb-0.5">
              Next Step
            </h4>
            <p className="text-xs text-[var(--text-primary)]">
              {result.next_step}
            </p>
          </div>
        )}
      </div>

      {/* Technical Details Toggle */}
      <div className="border-t border-[var(--border)]">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="w-full px-5 py-2 text-left text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider hover:bg-[var(--bg-hover)] transition-colors"
        >
          {showDetails ? "Hide Technical Details" : "Show Technical Details"}
        </button>
        {showDetails && (
          <div className="px-5 py-3 bg-[var(--bg-primary)]">
            <pre className="text-[11px] text-[var(--text-secondary)] overflow-x-auto whitespace-pre-wrap font-mono">
              {JSON.stringify(result.data, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
