"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import type { Job } from "@/lib/types";

const STATUS_STYLES: Record<string, { dot: string; label: string; color: string }> = {
  queued: { dot: "bg-[var(--text-muted)]", label: "Queued", color: "var(--text-muted)" },
  running: { dot: "bg-[var(--accent-blue)] animate-pulse", label: "Running", color: "var(--accent-blue)" },
  completed: { dot: "bg-[var(--accent-green)]", label: "Completed", color: "var(--accent-green)" },
  failed: { dot: "bg-[var(--accent-red)]", label: "Failed", color: "var(--accent-red)" },
};

const TYPE_LABELS: Record<string, string> = {
  battery_benchmark: "Battery Benchmark",
  battery_validation: "Battery Validation",
  pv_benchmark: "PV Benchmark",
  pv_validation: "PV Validation",
  research: "Research Run",
  diligence: "Due Diligence",
};

const AREA_LINKS: Record<string, string> = {
  validate: "/validate",
  research: "/research",
  diligence: "/diligence",
};

function formatTimestamp(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

export default function JobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params.id as string;

  const [job, setJob] = useState<Job | null>(null);
  const [log, setLog] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showLog, setShowLog] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [rerunning, setRerunning] = useState(false);

  const fetchJob = useCallback(async () => {
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (res.ok) {
        const data = await res.json();
        setJob(data.job);
        setLog(data.log);
      }
    } catch {
      // Keep stale
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    fetchJob();
    // Poll while running
    const timer = setInterval(() => {
      fetchJob();
    }, 3000);
    return () => clearInterval(timer);
  }, [fetchJob]);

  const handleRerun = async () => {
    if (!job) return;
    setRerunning(true);
    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: job.type, config: job.config }),
      });
      if (res.ok) {
        const data = await res.json();
        router.push(`/jobs/${data.job.id}`);
      }
    } catch {
      // Silent
    } finally {
      setRerunning(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 max-w-4xl">
        <p className="text-sm text-[var(--text-muted)]">Loading job...</p>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="p-8 max-w-4xl">
        <p className="text-sm text-[var(--accent-red)]">Job not found: {jobId}</p>
        <Link href="/" className="text-xs text-[var(--accent-blue)] hover:underline mt-2 inline-block">
          Back to Home
        </Link>
      </div>
    );
  }

  const status = STATUS_STYLES[job.status] ?? STATUS_STYLES.queued;

  return (
    <div className="p-8 max-w-4xl">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] mb-6">
        <Link href="/" className="hover:text-[var(--accent-blue)]">Home</Link>
        <span>/</span>
        <Link href={AREA_LINKS[job.product_area] || "/"} className="hover:text-[var(--accent-blue)]">
          {job.product_area.charAt(0).toUpperCase() + job.product_area.slice(1)}
        </Link>
        <span>/</span>
        <span className="text-[var(--text-secondary)]">{job.id.slice(0, 24)}...</span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <span className={`w-3 h-3 rounded-full ${status.dot}`} />
            <h1 className="text-xl font-bold text-[var(--text-primary)]">
              {TYPE_LABELS[job.type] || job.type}
            </h1>
            <span
              className="text-xs px-2 py-0.5 rounded-full border"
              style={{ color: status.color, borderColor: status.color }}
            >
              {status.label}
            </span>
          </div>
          <p className="text-xs text-[var(--text-muted)] font-mono">{job.id}</p>
        </div>
        <button
          onClick={handleRerun}
          disabled={rerunning}
          className="text-xs px-3 py-1.5 rounded border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent-blue)]/40 transition-colors disabled:opacity-50"
        >
          {rerunning ? "Creating..." : "Rerun with same config"}
        </button>
      </div>

      {/* Timeline */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Lifecycle
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
          <div className="grid grid-cols-4 divide-x divide-[var(--border)]">
            <div className="px-4 py-3">
              <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-1">Created</p>
              <p className="text-xs text-[var(--text-primary)]">{formatTimestamp(job.created_at)}</p>
            </div>
            <div className="px-4 py-3">
              <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-1">Started</p>
              <p className="text-xs text-[var(--text-primary)]">{formatTimestamp(job.started_at)}</p>
            </div>
            <div className="px-4 py-3">
              <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-1">Completed</p>
              <p className="text-xs text-[var(--text-primary)]">{formatTimestamp(job.completed_at)}</p>
            </div>
            <div className="px-4 py-3">
              <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-1">Duration</p>
              <p className="text-xs text-[var(--text-primary)]">
                {formatDuration(job.started_at, job.completed_at)}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Details */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Details
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] divide-y divide-[var(--border)]">
          <div className="flex justify-between px-4 py-2.5">
            <span className="text-xs text-[var(--text-muted)]">Type</span>
            <span className="text-xs text-[var(--text-primary)]">{TYPE_LABELS[job.type] || job.type}</span>
          </div>
          <div className="flex justify-between px-4 py-2.5">
            <span className="text-xs text-[var(--text-muted)]">Product Area</span>
            <span className="text-xs text-[var(--text-primary)]">{job.product_area}</span>
          </div>
          <div className="flex justify-between px-4 py-2.5">
            <span className="text-xs text-[var(--text-muted)]">Domain</span>
            <span className="text-xs text-[var(--text-primary)]">{job.domain}</span>
          </div>
          {job.result_id && (
            <div className="flex justify-between px-4 py-2.5">
              <span className="text-xs text-[var(--text-muted)]">Result Brief</span>
              <span className="text-xs text-[var(--accent-blue)] font-mono">{job.result_id}</span>
            </div>
          )}
          {job.error && (
            <div className="px-4 py-2.5">
              <span className="text-xs text-[var(--accent-red)] block mb-1">Error</span>
              <pre className="text-[10px] text-[var(--accent-red)] whitespace-pre-wrap font-mono leading-relaxed">
                {job.error}
              </pre>
            </div>
          )}
        </div>
      </section>

      {/* Config */}
      <section className="mb-8">
        <button
          onClick={() => setShowConfig(!showConfig)}
          className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider hover:text-[var(--text-secondary)] transition-colors"
        >
          {showConfig ? "Hide Config" : "Show Config"}
        </button>
        {showConfig && (
          <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] overflow-hidden">
            <pre className="p-4 text-[10px] text-[var(--text-secondary)] font-mono leading-relaxed overflow-auto select-all">
              {JSON.stringify(job.config, null, 2)}
            </pre>
          </div>
        )}
      </section>

      {/* Output Log */}
      <section className="mb-8">
        <button
          onClick={() => setShowLog(!showLog)}
          className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider hover:text-[var(--text-secondary)] transition-colors"
        >
          {showLog ? "Hide Output Log" : "Show Output Log"}
        </button>
        {showLog && (
          <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] overflow-hidden">
            {log ? (
              <pre className="p-4 text-[10px] text-[var(--text-secondary)] font-mono leading-relaxed overflow-auto max-h-96 select-all">
                {log}
              </pre>
            ) : (
              <p className="p-4 text-xs text-[var(--text-muted)]">
                {job.status === "running" || job.status === "queued"
                  ? "Log will be available after job completes."
                  : "No output log available."}
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
