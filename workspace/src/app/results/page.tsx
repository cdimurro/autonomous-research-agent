export default function ResultsPage() {
  return (
    <div className="p-8 max-w-6xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-xl font-bold text-[var(--text-primary)]">
          Results
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Inspect all outputs, decision briefs, diagnostics, and raw artifacts
        </p>
      </div>

      {/* Filters */}
      <section className="mb-6">
        <div className="flex items-center gap-3">
          <select className="bg-[var(--bg-card)] border border-[var(--border)] rounded px-3 py-1.5 text-xs text-[var(--text-secondary)] focus:outline-none focus:border-[var(--accent-blue)]/50">
            <option value="all">All Types</option>
            <option value="validation">Validation</option>
            <option value="research">Research</option>
            <option value="diligence">Due Diligence</option>
            <option value="brief">Decision Brief</option>
          </select>
          <select className="bg-[var(--bg-card)] border border-[var(--border)] rounded px-3 py-1.5 text-xs text-[var(--text-secondary)] focus:outline-none focus:border-[var(--accent-blue)]/50">
            <option value="all">All Domains</option>
            <option value="battery">Battery</option>
            <option value="pv">PV</option>
          </select>
          <input
            type="text"
            placeholder="Search results..."
            className="flex-1 bg-[var(--bg-card)] border border-[var(--border)] rounded px-3 py-1.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50"
          />
        </div>
      </section>

      {/* Results List — placeholder, wired in CC-BE-2456 */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Recent Runs
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
          <p className="text-sm text-[var(--text-muted)] text-center">
            Results from completed jobs will appear here.
          </p>
        </div>
      </section>

      {/* Artifact Inspector — placeholder, wired in CC-BE-2456 */}
      <section>
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Artifact Inspector
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
          <p className="text-sm text-[var(--text-muted)] text-center">
            Select a result above to inspect its artifacts and raw JSON.
          </p>
        </div>
      </section>
    </div>
  );
}
