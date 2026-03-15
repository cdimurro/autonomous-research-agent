"use client";

import { useState, useEffect, useCallback } from "react";
import { useBriefs } from "@/hooks/useBriefs";
import DecisionBriefCard from "@/components/results/DecisionBriefCard";
import ArtifactGrid from "@/components/results/ArtifactGrid";
import type { BriefType, ResearchBrief, DiligenceBrief } from "@/lib/types";

type TabId = "briefs" | "compare" | "artifacts";

interface ArtifactItem {
  name: string;
  path: string;
  size: number;
  modified_at: string;
}

const BRIEF_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  decision: { label: "Decision", color: "var(--accent-blue)" },
  research: { label: "Research", color: "var(--accent-purple)" },
  diligence: { label: "Diligence", color: "var(--accent-amber)" },
};

// ── Compact brief cards for Research and Diligence in Results ────────────

function ResearchBriefResultCard({
  brief,
  selected,
  onSelect,
}: {
  brief: ResearchBrief;
  selected: boolean;
  onSelect: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`rounded-lg border overflow-hidden transition-colors ${
        selected
          ? "border-[var(--accent-purple)]/60 bg-[var(--accent-purple)]/5"
          : "border-[var(--border)] bg-[var(--bg-card)]"
      }`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-4 py-3 hover:bg-[var(--bg-hover)] transition-colors"
      >
        <div className="flex items-center gap-2 mb-1">
          <span
            className="text-[9px] px-1.5 py-0.5 rounded-full border"
            style={{ color: "var(--accent-purple)", borderColor: "var(--accent-purple)" }}
          >
            Research
          </span>
          <span className="text-[9px] text-[var(--text-muted)]">{brief.domain}</span>
          <span className="text-[9px] text-[var(--text-muted)]">
            Evidence: {brief.evidence_quality}
          </span>
        </div>
        <h3 className="text-sm font-medium text-[var(--text-primary)] leading-tight">
          {brief.headline}
        </h3>
        <p className="text-xs text-[var(--text-secondary)] mt-0.5 line-clamp-2">
          {brief.summary}
        </p>
      </button>

      {expanded && (
        <div className="border-t border-[var(--border)] px-4 py-3 space-y-3">
          {brief.promising_directions.length > 0 && (
            <div>
              <h4 className="text-[10px] font-semibold text-[var(--accent-green)] uppercase tracking-wider mb-1">
                Promising ({brief.promising_directions.length})
              </h4>
              {brief.promising_directions.map((d, i) => (
                <p key={i} className="text-xs text-[var(--text-secondary)] leading-snug">
                  &bull; {d.title} ({d.confidence})
                </p>
              ))}
            </div>
          )}
          {brief.recommended_next && (
            <div className="bg-[var(--accent-purple)]/5 border border-[var(--accent-purple)]/20 rounded px-3 py-2">
              <p className="text-xs text-[var(--text-primary)]">{brief.recommended_next}</p>
            </div>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onSelect(); }}
            className={`text-[10px] px-2 py-1 rounded border transition-colors ${
              selected
                ? "border-[var(--accent-purple)]/60 text-[var(--accent-purple)]"
                : "border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent-purple)]/40"
            }`}
          >
            {selected ? "Selected for compare" : "Select for compare"}
          </button>
        </div>
      )}
    </div>
  );
}

function DiligenceBriefResultCard({
  brief,
  selected,
  onSelect,
}: {
  brief: DiligenceBrief;
  selected: boolean;
  onSelect: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`rounded-lg border overflow-hidden transition-colors ${
        selected
          ? "border-[var(--accent-amber)]/60 bg-[var(--accent-amber)]/5"
          : "border-[var(--border)] bg-[var(--bg-card)]"
      }`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-4 py-3 hover:bg-[var(--bg-hover)] transition-colors"
      >
        <div className="flex items-center gap-2 mb-1">
          <span
            className="text-[9px] px-1.5 py-0.5 rounded-full border"
            style={{ color: "var(--accent-amber)", borderColor: "var(--accent-amber)" }}
          >
            Diligence
          </span>
          {brief.focus_areas.slice(0, 2).map((fa) => (
            <span key={fa} className="text-[9px] text-[var(--text-muted)]">{fa}</span>
          ))}
        </div>
        <h3 className="text-sm font-medium text-[var(--text-primary)] leading-tight">
          {brief.headline}
        </h3>
        <p className="text-xs text-[var(--text-secondary)] mt-0.5 line-clamp-2">
          {brief.summary}
        </p>
      </button>

      {expanded && (
        <div className="border-t border-[var(--border)] px-4 py-3 space-y-3">
          {brief.strongest_signals.length > 0 && (
            <div>
              <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1">
                Signals ({brief.strongest_signals.length})
              </h4>
              {brief.strongest_signals.map((s, i) => (
                <p key={i} className="text-xs text-[var(--text-secondary)] leading-snug">
                  &bull; {s.title} ({s.signal_type})
                </p>
              ))}
            </div>
          )}
          {brief.recommendation && (
            <div className="bg-[var(--accent-amber)]/5 border border-[var(--accent-amber)]/20 rounded px-3 py-2">
              <p className="text-xs text-[var(--text-primary)]">{brief.recommendation}</p>
            </div>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onSelect(); }}
            className={`text-[10px] px-2 py-1 rounded border transition-colors ${
              selected
                ? "border-[var(--accent-amber)]/60 text-[var(--accent-amber)]"
                : "border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent-amber)]/40"
            }`}
          >
            {selected ? "Selected for compare" : "Select for compare"}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Comparison View ─────────────────────────────────────────────────────

function ComparisonView({
  briefs,
  onClear,
}: {
  briefs: Record<string, unknown>[];
  onClear: () => void;
}) {
  const [copied, setCopied] = useState(false);

  if (briefs.length < 2) {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-8 text-center">
        <p className="text-sm text-[var(--text-muted)]">
          Select 2 briefs to compare. Use the &ldquo;Select for compare&rdquo; button on any brief card.
        </p>
        <p className="text-xs text-[var(--text-muted)] mt-2">
          {briefs.length}/2 selected
        </p>
      </div>
    );
  }

  const [a, b] = briefs;
  const typeA = (a.brief_type as string) || "decision";
  const typeB = (b.brief_type as string) || "decision";

  const handleCopyJson = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify({ comparison: [a, b] }, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--text-muted)]">
          Comparing 2 briefs ({typeA} vs {typeB})
        </p>
        <div className="flex gap-2">
          <button
            onClick={handleCopyJson}
            className="text-[10px] px-2 py-1 rounded border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            {copied ? "Copied!" : "Copy JSON"}
          </button>
          <button
            onClick={onClear}
            className="text-[10px] px-2 py-1 rounded border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {[a, b].map((brief, idx) => {
          const bt = (brief.brief_type as string) || "decision";
          const style = BRIEF_TYPE_LABELS[bt] || BRIEF_TYPE_LABELS.decision;
          return (
            <div key={idx} className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
              <div className="px-4 py-3 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="text-[9px] px-1.5 py-0.5 rounded-full border"
                    style={{ color: style.color, borderColor: style.color }}
                  >
                    {style.label}
                  </span>
                </div>
                <h3 className="text-sm font-medium text-[var(--text-primary)] leading-tight">
                  {(brief.title as string) || (brief.headline as string)}
                </h3>
              </div>
              <div className="px-4 py-3 space-y-2">
                {/* Universal fields */}
                <p className="text-xs text-[var(--text-secondary)] leading-snug">
                  {(brief.headline as string) || (brief.summary as string)}
                </p>

                {bt === "decision" && (
                  <>
                    <div className="flex justify-between text-xs">
                      <span className="text-[var(--text-muted)]">Score</span>
                      <span className="text-[var(--text-primary)] font-mono font-bold">
                        {(brief.final_score as number)?.toFixed(3) || "N/A"}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-[var(--text-muted)]">Family</span>
                      <span className="text-[var(--text-primary)]">
                        {brief.candidate_family as string}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-[var(--text-muted)]">Confidence</span>
                      <span className="text-[var(--text-primary)]">
                        {brief.confidence_tier as string}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-[var(--text-muted)]">Sidecar</span>
                      <span className="text-[var(--text-primary)]">
                        {brief.sidecar_gate_decision as string}
                      </span>
                    </div>
                    {(brief.caveats as string[])?.length > 0 && (
                      <div>
                        <span className="text-[10px] text-[var(--accent-amber)]">
                          {(brief.caveats as string[]).length} caveats
                        </span>
                      </div>
                    )}
                  </>
                )}

                {bt === "research" && (
                  <>
                    <div className="flex justify-between text-xs">
                      <span className="text-[var(--text-muted)]">Evidence</span>
                      <span className="text-[var(--text-primary)]">
                        {(brief as unknown as ResearchBrief).evidence_quality}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-[var(--text-muted)]">Directions</span>
                      <span className="text-[var(--text-primary)]">
                        {(brief as unknown as ResearchBrief).promising_directions?.length || 0} promising
                      </span>
                    </div>
                    {(brief as unknown as ResearchBrief).recommended_next && (
                      <p className="text-[10px] text-[var(--text-secondary)] bg-[var(--bg-primary)] rounded px-2 py-1">
                        Next: {(brief as unknown as ResearchBrief).recommended_next}
                      </p>
                    )}
                  </>
                )}

                {bt === "diligence" && (
                  <>
                    <div className="flex justify-between text-xs">
                      <span className="text-[var(--text-muted)]">Signals</span>
                      <span className="text-[var(--text-primary)]">
                        {(brief as unknown as DiligenceBrief).strongest_signals?.length || 0}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-[var(--text-muted)]">Risks</span>
                      <span className="text-[var(--text-primary)]">
                        {(brief as unknown as DiligenceBrief).risks?.length || 0}
                      </span>
                    </div>
                    {(brief as unknown as DiligenceBrief).recommendation && (
                      <p className="text-[10px] text-[var(--text-secondary)] bg-[var(--bg-primary)] rounded px-2 py-1">
                        {(brief as unknown as DiligenceBrief).recommendation}
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── JSON Inspector ──────────────────────────────────────────────────────

function JsonInspector({ data }: { data: Record<string, unknown> }) {
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(data, null, 2);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(json);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
  };

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border)]">
        <span className="text-[10px] font-semibold text-[var(--text-muted)]">
          JSON
        </span>
        <button
          onClick={handleCopy}
          className="text-[10px] px-2 py-0.5 rounded border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <pre className="p-3 text-[10px] text-[var(--text-secondary)] overflow-auto font-mono leading-relaxed max-h-96 select-all">
        {json}
      </pre>
    </div>
  );
}

// ── Main Results Page ───────────────────────────────────────────────────

export default function ResultsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("briefs");
  const { briefs: allBriefs, loading: briefsLoading } = useBriefs();

  // Artifact state
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);

  // Filter state
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<BriefType | "all">("all");

  // Comparison state
  const [compareIds, setCompareIds] = useState<string[]>([]);

  // JSON inspector
  const [inspectBrief, setInspectBrief] = useState<Record<string, unknown> | null>(null);

  const fetchArtifacts = useCallback(async () => {
    setArtifactsLoading(true);
    try {
      const res = await fetch("/api/artifacts");
      if (res.ok) {
        const data = await res.json();
        setArtifacts(data.artifacts);
      }
    } catch {
      // Keep stale
    } finally {
      setArtifactsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === "artifacts") {
      fetchArtifacts();
    }
  }, [activeTab, fetchArtifacts]);

  // Filter briefs
  const filteredBriefs = allBriefs.filter((b) => {
    const bt = (b.brief_type as string) || "decision";
    if (typeFilter !== "all" && bt !== typeFilter) return false;
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    const searchable = [
      b.title,
      b.headline,
      b.candidate_family,
      b.chemistry,
      b.id,
      b.topic,
      b.subject,
      b.summary,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return searchable.includes(q);
  });

  // Filter artifacts by search
  const filteredArtifacts = artifacts.filter((a) => {
    if (!searchQuery) return true;
    return a.name.toLowerCase().includes(searchQuery.toLowerCase());
  });

  const toggleCompare = (briefId: string) => {
    setCompareIds((prev) => {
      if (prev.includes(briefId)) return prev.filter((id) => id !== briefId);
      if (prev.length >= 2) return [prev[1], briefId]; // Replace oldest
      return [...prev, briefId];
    });
  };

  const compareBriefs = allBriefs.filter((b) =>
    compareIds.includes(b.id as string)
  );

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-[var(--text-primary)]">
          Results
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Inspect all outputs, decision briefs, diagnostics, and raw artifacts
        </p>
      </div>

      {/* Tabs + Search + Type Filter */}
      <div className="flex items-center gap-4 mb-6 flex-wrap">
        <div className="flex border border-[var(--border)] rounded overflow-hidden">
          {(["briefs", "compare", "artifacts"] as TabId[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 text-xs transition-colors ${
                activeTab === tab
                  ? "bg-[var(--accent-blue)]/15 text-[var(--accent-blue)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
              }`}
            >
              {tab === "briefs"
                ? "All Briefs"
                : tab === "compare"
                ? `Compare${compareIds.length > 0 ? ` (${compareIds.length})` : ""}`
                : "Artifacts"}
            </button>
          ))}
        </div>

        {activeTab === "briefs" && (
          <div className="flex border border-[var(--border)] rounded overflow-hidden">
            {(["all", "decision", "research", "diligence"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTypeFilter(t)}
                className={`px-3 py-1.5 text-xs transition-colors ${
                  typeFilter === t
                    ? "bg-[var(--bg-hover)] text-[var(--text-primary)]"
                    : "text-[var(--text-muted)] hover:bg-[var(--bg-hover)]"
                }`}
              >
                {t === "all" ? "All" : BRIEF_TYPE_LABELS[t]?.label || t}
              </button>
            ))}
          </div>
        )}

        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search..."
          className="flex-1 min-w-48 bg-[var(--bg-card)] border border-[var(--border)] rounded px-3 py-1.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50"
        />
      </div>

      {/* Briefs Tab */}
      {activeTab === "briefs" && (
        <div>
          {briefsLoading ? (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
              <p className="text-sm text-[var(--text-muted)] text-center">
                Loading briefs...
              </p>
            </div>
          ) : filteredBriefs.length === 0 ? (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
              <p className="text-sm text-[var(--text-muted)] text-center">
                {searchQuery || typeFilter !== "all"
                  ? "No briefs match your filters."
                  : "No briefs yet. Run a workflow to generate results."}
              </p>
            </div>
          ) : (
            <div>
              <p className="text-[10px] text-[var(--text-muted)] mb-2">
                {filteredBriefs.length} brief{filteredBriefs.length !== 1 ? "s" : ""}
              </p>
              <div className="grid grid-cols-2 gap-3">
                {filteredBriefs.map((brief) => {
                  const bt = (brief.brief_type as string) || "decision";
                  const isSelected = compareIds.includes(brief.id as string);

                  if (bt === "decision") {
                    return (
                      <div key={brief.id as string} className="relative">
                        <DecisionBriefCard
                          brief={brief as Parameters<typeof DecisionBriefCard>[0]["brief"]}
                          defaultExpanded
                          compact
                        />
                        <div className="absolute top-2 right-2 flex gap-1.5">
                          <button
                            onClick={() => setInspectBrief(brief)}
                            className="text-[9px] px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] bg-[var(--bg-card)] transition-colors"
                            title="View JSON"
                          >
                            JSON
                          </button>
                          <button
                            onClick={() => toggleCompare(brief.id as string)}
                            className={`text-[9px] px-1.5 py-0.5 rounded border bg-[var(--bg-card)] transition-colors ${
                              isSelected
                                ? "border-[var(--accent-blue)]/60 text-[var(--accent-blue)]"
                                : "border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                            }`}
                            title="Select for comparison"
                          >
                            {isSelected ? "Selected" : "Compare"}
                          </button>
                        </div>
                      </div>
                    );
                  }

                  if (bt === "research") {
                    return (
                      <div key={brief.id as string} className="relative">
                        <ResearchBriefResultCard
                          brief={brief as unknown as ResearchBrief}
                          selected={isSelected}
                          onSelect={() => toggleCompare(brief.id as string)}
                        />
                        <button
                          onClick={() => setInspectBrief(brief)}
                          className="absolute top-2 right-2 text-[9px] px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] bg-[var(--bg-card)] transition-colors"
                          title="View JSON"
                        >
                          JSON
                        </button>
                      </div>
                    );
                  }

                  if (bt === "diligence") {
                    return (
                      <div key={brief.id as string} className="relative">
                        <DiligenceBriefResultCard
                          brief={brief as unknown as DiligenceBrief}
                          selected={isSelected}
                          onSelect={() => toggleCompare(brief.id as string)}
                        />
                        <button
                          onClick={() => setInspectBrief(brief)}
                          className="absolute top-2 right-2 text-[9px] px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] bg-[var(--bg-card)] transition-colors"
                          title="View JSON"
                        >
                          JSON
                        </button>
                      </div>
                    );
                  }

                  return null;
                })}
              </div>
            </div>
          )}

          {/* JSON Inspector Drawer */}
          {inspectBrief && (
            <div className="mt-6">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                  JSON Inspector
                </h3>
                <button
                  onClick={() => setInspectBrief(null)}
                  className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                >
                  Close
                </button>
              </div>
              <JsonInspector data={inspectBrief} />
            </div>
          )}
        </div>
      )}

      {/* Compare Tab */}
      {activeTab === "compare" && (
        <ComparisonView
          briefs={compareBriefs}
          onClear={() => setCompareIds([])}
        />
      )}

      {/* Artifacts Tab — 2x2 grid */}
      {activeTab === "artifacts" && (
        <div>
          {artifactsLoading ? (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
              <p className="text-xs text-[var(--text-muted)] text-center">
                Loading...
              </p>
            </div>
          ) : (
            <ArtifactGrid artifacts={filteredArtifacts} />
          )}
        </div>
      )}
    </div>
  );
}
