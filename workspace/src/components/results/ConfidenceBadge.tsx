const TIER_STYLES: Record<string, { bg: string; text: string; label: string }> =
  {
    high: {
      bg: "bg-[var(--accent-green)]/15",
      text: "text-[var(--accent-green)]",
      label: "High Confidence",
    },
    standard: {
      bg: "bg-[var(--accent-blue)]/15",
      text: "text-[var(--accent-blue)]",
      label: "Standard Confidence",
    },
    low: {
      bg: "bg-[var(--accent-amber)]/15",
      text: "text-[var(--accent-amber)]",
      label: "Low Confidence",
    },
    unverified: {
      bg: "bg-[var(--accent-red)]/15",
      text: "text-[var(--accent-red)]",
      label: "Unverified",
    },
  };

export default function ConfidenceBadge({ tier }: { tier: string }) {
  const style = TIER_STYLES[tier] ?? TIER_STYLES.unverified;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium ${style.bg} ${style.text}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {style.label}
    </span>
  );
}
