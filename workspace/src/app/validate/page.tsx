export default function ValidatePage() {
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
          <button className="text-left rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-4 hover:border-[var(--accent-blue)]/40 transition-colors">
            <div className="text-sm font-medium text-[var(--text-primary)]">
              Battery ECM + Cycle
            </div>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              Thevenin 1RC + PyBaMM DFN sidecar &middot; 11 families &middot; 9
              metrics
            </p>
          </button>
          <button className="text-left rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-4 hover:border-[var(--accent-blue)]/40 transition-colors">
            <div className="text-sm font-medium text-[var(--text-primary)]">
              PV I-V Characterization
            </div>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              pvlib single-diode &middot; 6 families &middot; 5 metrics
            </p>
          </button>
        </div>
      </section>

      {/* Validation Form — placeholder, wired in CC-BE-2454 */}
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
              placeholder="Random seed for reproducibility"
              className="w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
              <input
                type="checkbox"
                className="rounded border-[var(--border)]"
              />
              Mock sidecar (skip PyBaMM)
            </label>
          </div>
          <button className="px-4 py-2 bg-[var(--accent-blue)] text-white text-sm rounded hover:bg-[var(--accent-blue)]/80 transition-colors">
            Run Validation
          </button>
        </div>
      </section>

      {/* Results Area — placeholder, wired in CC-BE-2455 */}
      <section>
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Validation Results
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
          <p className="text-sm text-[var(--text-muted)] text-center">
            Run a validation to see results here.
          </p>
        </div>
      </section>
    </div>
  );
}
