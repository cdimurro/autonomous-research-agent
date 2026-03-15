export default function DiligencePage() {
  return (
    <div className="p-8 max-w-5xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-xl font-bold text-[var(--text-primary)]">
          Due Diligence
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Assess companies, technologies, and market opportunities with
          simulation-backed analysis
        </p>
      </div>

      {/* Diligence Input */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Assessment Scope
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 space-y-4">
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1.5">
              Company or Technology
            </label>
            <input
              type="text"
              placeholder="Company name, technology, or market area..."
              className="w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50"
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1.5">
              Analysis Focus
            </label>
            <div className="flex flex-wrap gap-2">
              {[
                "Technical Validation",
                "Market Assessment",
                "Risk Analysis",
                "Competitive Landscape",
              ].map((focus) => (
                <label
                  key={focus}
                  className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)] bg-[var(--bg-primary)] border border-[var(--border)] rounded px-2.5 py-1.5 cursor-pointer hover:border-[var(--accent-amber)]/40"
                >
                  <input
                    type="checkbox"
                    className="rounded border-[var(--border)]"
                  />
                  {focus}
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1.5">
              Additional Context
            </label>
            <textarea
              rows={3}
              placeholder="Any additional context, constraints, or specific questions..."
              className="w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50 resize-none"
            />
          </div>
          <button className="px-4 py-2 bg-[var(--accent-amber)] text-black text-sm font-medium rounded hover:bg-[var(--accent-amber)]/80 transition-colors">
            Run Due Diligence
          </button>
        </div>
      </section>

      {/* Assessment Results — placeholder */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Key Signals
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
          <p className="text-sm text-[var(--text-muted)] text-center">
            Run a diligence assessment to see key signals here.
          </p>
        </div>
      </section>

      <section>
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Risks &amp; Open Questions
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
          <p className="text-sm text-[var(--text-muted)] text-center">
            Identified risks and open questions will appear here.
          </p>
        </div>
      </section>
    </div>
  );
}
