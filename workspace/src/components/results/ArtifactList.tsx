"use client";

interface ArtifactItem {
  name: string;
  path: string;
  size: number;
  modified_at: string;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ArtifactList({
  artifacts,
  onSelect,
  selectedPath,
}: {
  artifacts: ArtifactItem[];
  onSelect: (path: string) => void;
  selectedPath: string | null;
}) {
  if (artifacts.length === 0) {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6">
        <p className="text-sm text-[var(--text-muted)] text-center">
          No artifacts found.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
      {artifacts.map((a) => (
        <button
          key={a.path}
          onClick={() => onSelect(a.path)}
          className={`w-full text-left flex items-center justify-between px-4 py-2.5 border-b border-[var(--border)] last:border-b-0 transition-colors ${
            selectedPath === a.path
              ? "bg-[var(--accent-blue)]/10"
              : "hover:bg-[var(--bg-hover)]"
          }`}
        >
          <div className="min-w-0 flex-1">
            <p className="text-xs text-[var(--text-primary)] truncate">
              {a.name}
            </p>
            <p className="text-[10px] text-[var(--text-muted)]">
              {new Date(a.modified_at).toLocaleString()}
            </p>
          </div>
          <span className="text-[10px] text-[var(--text-muted)] ml-3 shrink-0">
            {formatSize(a.size)}
          </span>
        </button>
      ))}
    </div>
  );
}
