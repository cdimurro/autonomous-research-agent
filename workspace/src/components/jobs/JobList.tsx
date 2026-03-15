"use client";

import type { Job } from "@/lib/types";
import JobStatusCard from "./JobStatusCard";

export default function JobList({ jobs }: { jobs: Job[] }) {
  if (jobs.length === 0) {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
        <p className="text-sm text-[var(--text-muted)] text-center">
          No jobs yet. Launch a workflow to get started.
        </p>
      </div>
    );
  }

  // Group by status
  const running = jobs.filter((j) => j.status === "running");
  const queued = jobs.filter((j) => j.status === "queued");
  const recent = jobs
    .filter((j) => j.status === "completed" || j.status === "failed")
    .slice(0, 10);

  return (
    <div className="space-y-3">
      {/* Active jobs */}
      {(running.length > 0 || queued.length > 0) && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
          <div className="px-4 py-2 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
            <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Active ({running.length + queued.length})
            </span>
          </div>
          {[...running, ...queued].map((job) => (
            <JobStatusCard key={job.id} job={job} />
          ))}
        </div>
      )}

      {/* Recent completed/failed */}
      {recent.length > 0 && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
          <div className="px-4 py-2 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
            <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Recent ({recent.length})
            </span>
          </div>
          {recent.map((job) => (
            <JobStatusCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </div>
  );
}
