"use client";

export default function AssistantToggle({
  isOpen,
  onToggle,
}: {
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className={`fixed bottom-6 right-6 z-50 w-10 h-10 rounded-full flex items-center justify-center shadow-lg transition-colors ${
        isOpen
          ? "bg-[var(--accent-blue)] text-white"
          : "bg-[var(--bg-card)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent-blue)]/40"
      }`}
      title="Toggle AI Assistant"
    >
      <span className="text-sm font-bold">AI</span>
    </button>
  );
}
