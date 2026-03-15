"use client";

import Link from "next/link";
import type { Job } from "@/lib/types";

const STATUS_STYLES: Record<string, { dot: string; label: string }> = {
  queued: { dot: "bg-[var(--text-muted)]", label: "Queued" },
  running: { dot: "bg-[var(--accent-blue)] animate-pulse", label: "Running" },
  completed: { dot: "bg-[var(--accent-green)]", label: "Completed" },
  failed: { dot: "bg-[var(--accent-red)]", label: "Failed" },
};

const TYPE_LABELS: Record<string, string> = {
  battery_benchmark: "Battery Benchmark",
  battery_validation: "Battery Validation",
  pv_benchmark: "PV Benchmark",
  pv_validation: "PV Validation",
  research: "Research Run",
  diligence: "Due Diligence",
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function JobStatusCard({ job }: { job: Job }) {
  const style = STATUS_STYLES[job.status] ?? STATUS_STYLES.queued;
  const typeLabel = TYPE_LABELS[job.type] ?? job.type;

  return (
    <Link
      href={`/jobs/${job.id}`}
      className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--bg-hover)] transition-colors"
    >
      <div className="flex items-center gap-3">
        <span className={`w-2 h-2 rounded-full ${style.dot}`} />
        <div>
          <p className="text-sm text-[var(--text-primary)]">{typeLabel}</p>
          <p className="text-[10px] text-[var(--text-muted)]">
            {job.id.slice(0, 20)}... &middot; {timeAgo(job.created_at)}
          </p>
        </div>
      </div>
      <div className="text-right">
        <span
          className={`text-xs ${
            job.status === "failed"
              ? "text-[var(--accent-red)]"
              : job.status === "completed"
              ? "text-[var(--accent-green)]"
              : job.status === "running"
              ? "text-[var(--accent-blue)]"
              : "text-[var(--text-muted)]"
          }`}
        >
          {style.label}
        </span>
        {job.error && (
          <p
            className="text-[10px] text-[var(--accent-red)] max-w-48 truncate mt-0.5"
            title={job.error}
          >
            {job.error}
          </p>
        )}
      </div>
    </Link>
  );
}
