export default function ScoreBar({
  label,
  value,
  max = 1,
}: {
  label: string;
  value: number;
  max?: number;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const color =
    pct >= 80
      ? "var(--accent-green)"
      : pct >= 60
      ? "var(--accent-blue)"
      : pct >= 40
      ? "var(--accent-amber)"
      : "var(--accent-red)";

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-[var(--text-secondary)] w-32 shrink-0 truncate">
        {label}
      </span>
      <div className="flex-1 h-2 bg-[var(--bg-primary)] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-xs text-[var(--text-primary)] w-12 text-right font-mono">
        {value.toFixed(3)}
      </span>
    </div>
  );
}
