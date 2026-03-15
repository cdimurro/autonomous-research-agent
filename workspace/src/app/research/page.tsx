export default function ResearchPage() {
  return (
    <div className="p-8 max-w-5xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-xl font-bold text-[var(--text-primary)]">
          Research
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Explore new solution directions, generate candidates, and review
          promising paths
        </p>
      </div>

      {/* Research Input */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Research Topic
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 space-y-4">
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1.5">
              Problem or Topic
            </label>
            <textarea
              rows={3}
              placeholder="Describe the energy problem or research direction to explore..."
              className="w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50 resize-none"
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1.5">
              Domain Focus
            </label>
            <select className="w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-blue)]/50">
              <option value="battery">Battery</option>
              <option value="pv">Photovoltaic</option>
              <option value="general">General Energy</option>
            </select>
          </div>
          <button className="px-4 py-2 bg-[var(--accent-purple)] text-white text-sm rounded hover:bg-[var(--accent-purple)]/80 transition-colors">
            Start Research
          </button>
        </div>
      </section>

      {/* Directions — placeholder */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Promising Directions
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
          <p className="text-sm text-[var(--text-muted)] text-center">
            Start a research run to discover promising directions.
          </p>
        </div>
      </section>

      {/* Rejected Directions — placeholder */}
      <section>
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Rejected Directions
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
          <p className="text-sm text-[var(--text-muted)] text-center">
            Rejected candidates and failed paths will appear here.
          </p>
        </div>
      </section>
    </div>
  );
}
