const GATE_STYLES: Record<string, { bg: string; text: string }> = {
  confirmed: {
    bg: "bg-[var(--accent-green)]/15",
    text: "text-[var(--accent-green)]",
  },
  caveat: {
    bg: "bg-[var(--accent-amber)]/15",
    text: "text-[var(--accent-amber)]",
  },
  veto: {
    bg: "bg-[var(--accent-red)]/15",
    text: "text-[var(--accent-red)]",
  },
  not_verified: {
    bg: "bg-[var(--bg-hover)]",
    text: "text-[var(--text-muted)]",
  },
};

export default function SidecarBadge({ decision }: { decision: string }) {
  const style = GATE_STYLES[decision] ?? GATE_STYLES.not_verified;
  const label =
    decision === "confirmed"
      ? "Sidecar Confirmed"
      : decision === "caveat"
      ? "Sidecar Caveat"
      : decision === "veto"
      ? "Sidecar Veto"
      : "Not Verified";

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium ${style.bg} ${style.text}`}
    >
      {label}
    </span>
  );
}
