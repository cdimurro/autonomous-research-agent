"use client";

import { useState } from "react";
import { useJobs } from "@/hooks/useJobs";
import JobList from "@/components/jobs/JobList";

type Domain = "battery" | "pv";

const DOMAINS: Array<{
  id: Domain;
  label: string;
  jobType: string;
  desc: string;
}> = [
  {
    id: "battery",
    label: "Battery ECM + Cycle",
    jobType: "battery_benchmark",
    desc: "Thevenin 1RC + PyBaMM DFN sidecar \u00b7 11 families \u00b7 9 metrics",
  },
  {
    id: "pv",
    label: "PV I-V Characterization",
    jobType: "pv_benchmark",
    desc: "pvlib single-diode \u00b7 6 families \u00b7 5 metrics",
  },
];

export default function ValidatePage() {
  const { jobs, submitJob } = useJobs();
  const [selectedDomain, setSelectedDomain] = useState<Domain>("battery");
  const [seed, setSeed] = useState("");
  const [mockSidecar, setMockSidecar] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const domainInfo = DOMAINS.find((d) => d.id === selectedDomain)!;

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const config: Record<string, unknown> = {};
      if (seed.trim()) config.seed = parseInt(seed, 10);
      if (mockSidecar) config.mock_sidecar = true;
      await submitJob(domainInfo.jobType, config);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit job");
    } finally {
      setSubmitting(false);
    }
  };

  const validationJobs = jobs.filter((j) => j.product_area === "validate");

  return (
    <div className="p-8 max-w-5xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-xl font-bold text-[var(--text-primary)]">
          Validate
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Evaluate technologies, candidates, and materials against benchmark
          loops
        </p>
      </div>

      {/* Domain Selector */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Select Domain
        </h2>
        <div className="grid grid-cols-2 gap-3">
          {DOMAINS.map(({ id, label, desc }) => (
            <button
              key={id}
              onClick={() => setSelectedDomain(id)}
              className={`text-left rounded-lg border p-4 transition-colors ${
                selectedDomain === id
                  ? "border-[var(--accent-blue)]/60 bg-[var(--accent-blue)]/10"
                  : "border-[var(--border)] bg-[var(--bg-card)] hover:border-[var(--accent-blue)]/40"
              }`}
            >
              <div className="text-sm font-medium text-[var(--text-primary)]">
                {label}
              </div>
              <p className="text-xs text-[var(--text-muted)] mt-1">{desc}</p>
            </button>
          ))}
        </div>
      </section>

      {/* Configuration */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Configuration
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 space-y-4">
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1.5">
              Seed (optional)
            </label>
            <input
              type="number"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              placeholder="Random seed for reproducibility"
              className="w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50"
            />
          </div>
          {selectedDomain === "battery" && (
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={mockSidecar}
                  onChange={(e) => setMockSidecar(e.target.checked)}
                  className="rounded border-[var(--border)]"
                />
                Mock sidecar (skip PyBaMM)
              </label>
            </div>
          )}
          {error && (
            <p className="text-xs text-[var(--accent-red)]">{error}</p>
          )}
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-2 bg-[var(--accent-blue)] text-white text-sm rounded hover:bg-[var(--accent-blue)]/80 transition-colors disabled:opacity-50"
          >
            {submitting ? "Submitting..." : "Run Validation"}
          </button>
        </div>
      </section>

      {/* Validation Jobs */}
      <section>
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Validation Jobs
        </h2>
        <JobList jobs={validationJobs} />
      </section>
    </div>
  );
}
