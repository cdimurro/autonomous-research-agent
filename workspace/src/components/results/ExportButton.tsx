"use client";

import { useState } from "react";

export default function ExportButton({
  briefId,
  className,
}: {
  briefId: string;
  className?: string;
}) {
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await fetch(`/api/briefs/export?id=${briefId}&format=json`);
      if (res.ok) {
        const data = await res.json();
        const markdown = data.markdown as string;
        // Download as file
        const blob = new Blob([markdown], { type: "text/markdown" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `brief_${briefId}.md`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {
      // Silent
    } finally {
      setExporting(false);
    }
  };

  return (
    <button
      onClick={handleExport}
      disabled={exporting}
      className={
        className ||
        "text-[10px] px-2 py-1 rounded border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:border-[var(--accent-blue)]/40 transition-colors disabled:opacity-50"
      }
    >
      {exporting ? "..." : "Export"}
    </button>
  );
}
