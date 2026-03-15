"use client";

import { useState, useEffect, useCallback } from "react";
import { useBriefs } from "@/hooks/useBriefs";
import DecisionBriefCard from "@/components/results/DecisionBriefCard";
import ArtifactList from "@/components/results/ArtifactList";
import JsonViewer from "@/components/results/JsonViewer";

type TabId = "briefs" | "artifacts";

interface ArtifactItem {
  name: string;
  path: string;
  size: number;
  modified_at: string;
}

export default function ResultsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("briefs");
  const { briefs, loading: briefsLoading } = useBriefs();

  // Artifact state
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);
  const [selectedArtifactPath, setSelectedArtifactPath] = useState<
    string | null
  >(null);
  const [artifactData, setArtifactData] = useState<unknown>(null);
  const [artifactLoading, setArtifactLoading] = useState(false);

  // Filter state
  const [searchQuery, setSearchQuery] = useState("");

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

  const loadArtifact = useCallback(async (path: string) => {
    setSelectedArtifactPath(path);
    setArtifactLoading(true);
    try {
      const res = await fetch(
        `/api/artifacts?path=${encodeURIComponent(path)}`
      );
      if (res.ok) {
        const data = await res.json();
        setArtifactData(data.data);
      }
    } catch {
      setArtifactData({ error: "Failed to load artifact" });
    } finally {
      setArtifactLoading(false);
    }
  }, []);

  // Filter briefs by search
  const filteredBriefs = briefs.filter((b) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    const searchable = [
      b.title,
      b.headline,
      b.candidate_family,
      b.chemistry,
      b.id,
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

  return (
    <div className="p-8 max-w-6xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-[var(--text-primary)]">
          Results
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Inspect all outputs, decision briefs, diagnostics, and raw artifacts
        </p>
      </div>

      {/* Tabs + Search */}
      <div className="flex items-center gap-4 mb-6">
        <div className="flex border border-[var(--border)] rounded overflow-hidden">
          {(["briefs", "artifacts"] as TabId[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 text-xs transition-colors ${
                activeTab === tab
                  ? "bg-[var(--accent-blue)]/15 text-[var(--accent-blue)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
              }`}
            >
              {tab === "briefs" ? "Decision Briefs" : "Artifacts"}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search..."
          className="flex-1 bg-[var(--bg-card)] border border-[var(--border)] rounded px-3 py-1.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50"
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
                {searchQuery
                  ? "No briefs match your search."
                  : "No decision briefs yet. Run a battery benchmark to generate results."}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-[10px] text-[var(--text-muted)]">
                {filteredBriefs.length} brief
                {filteredBriefs.length !== 1 ? "s" : ""}
              </p>
              {filteredBriefs.map((brief) => (
                <DecisionBriefCard
                  key={brief.id as string}
                  brief={
                    brief as Parameters<typeof DecisionBriefCard>[0]["brief"]
                  }
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Artifacts Tab */}
      {activeTab === "artifacts" && (
        <div className="grid grid-cols-[320px_1fr] gap-4">
          {/* Artifact list */}
          <div>
            <p className="text-[10px] text-[var(--text-muted)] mb-2">
              {filteredArtifacts.length} artifact
              {filteredArtifacts.length !== 1 ? "s" : ""} in runtime/
            </p>
            {artifactsLoading ? (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
                <p className="text-xs text-[var(--text-muted)] text-center">
                  Loading...
                </p>
              </div>
            ) : (
              <ArtifactList
                artifacts={filteredArtifacts}
                onSelect={loadArtifact}
                selectedPath={selectedArtifactPath}
              />
            )}
          </div>

          {/* Artifact viewer */}
          <div>
            {selectedArtifactPath ? (
              artifactLoading ? (
                <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
                  <p className="text-xs text-[var(--text-muted)] text-center">
                    Loading artifact...
                  </p>
                </div>
              ) : (
                <JsonViewer
                  data={artifactData}
                  title={
                    selectedArtifactPath.split("/").pop() ?? "Artifact"
                  }
                />
              )
            ) : (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
                <p className="text-sm text-[var(--text-muted)] text-center">
                  Select an artifact to inspect its contents.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
