"use client";

import Link from "next/link";
import { useJobs } from "@/hooks/useJobs";
import { useBriefs } from "@/hooks/useBriefs";
import JobList from "@/components/jobs/JobList";
import DecisionBriefCard from "@/components/results/DecisionBriefCard";

const QUICK_ACTIONS = [
  {
    label: "New Validation",
    href: "/validate",
    color: "var(--accent-blue)",
    desc: "Evaluate a technology or candidate",
  },
  {
    label: "New Research Run",
    href: "/research",
    color: "var(--accent-purple)",
    desc: "Explore promising directions",
  },
  {
    label: "New Diligence Run",
    href: "/diligence",
    color: "var(--accent-amber)",
    desc: "Assess a company or technology",
  },
  {
    label: "View Results",
    href: "/results",
    color: "var(--accent-green)",
    desc: "Inspect all outputs and artifacts",
  },
];

export default function HomePage() {
  const { jobs, loading } = useJobs();
  const { briefs, loading: briefsLoading } = useBriefs();

  return (
    <div className="p-8 max-w-5xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-xl font-bold text-[var(--text-primary)]">
          Control Room
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Internal development workspace &mdash; monitor jobs, launch workflows,
          inspect results
        </p>
      </div>

      {/* Quick Actions */}
      <section className="mb-10">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Quick Actions
        </h2>
        <div className="grid grid-cols-2 gap-3">
          {QUICK_ACTIONS.map(({ label, href, color, desc }) => (
            <Link
              key={href}
              href={href}
              className="group block rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-4 hover:border-[var(--accent-blue)]/40 transition-colors"
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ background: color }}
                />
                <span className="text-sm font-medium text-[var(--text-primary)] group-hover:text-[var(--accent-blue)] transition-colors">
                  {label}
                </span>
              </div>
              <p className="text-xs text-[var(--text-muted)]">{desc}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* Job Status */}
      <section className="mb-10">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Recent Jobs
        </h2>
        {loading ? (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
            <p className="text-sm text-[var(--text-muted)] text-center">
              Loading jobs...
            </p>
          </div>
        ) : (
          <JobList jobs={jobs} />
        )}
      </section>

      {/* Latest Decision Briefs */}
      <section>
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Latest Decision Briefs
        </h2>
        {briefsLoading ? (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
            <p className="text-sm text-[var(--text-muted)] text-center">
              Loading briefs...
            </p>
          </div>
        ) : briefs.length === 0 ? (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
            <p className="text-sm text-[var(--text-muted)] text-center">
              No decision briefs yet. Run a validation to generate results.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {briefs.slice(0, 3).map((brief) => (
              <DecisionBriefCard
                key={brief.id as string}
                brief={brief as Parameters<typeof DecisionBriefCard>[0]["brief"]}
              />
            ))}
            {briefs.length > 3 && (
              <Link
                href="/results"
                className="block text-center text-xs text-[var(--accent-blue)] hover:underline py-2"
              >
                View all {briefs.length} briefs
              </Link>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
