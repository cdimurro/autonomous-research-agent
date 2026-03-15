"use client";

import { useState } from "react";

export default function JsonViewer({
  data,
  title,
}: {
  data: unknown;
  title?: string;
}) {
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(data, null, 2);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(json);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback: select text
      const el = document.getElementById("json-viewer-pre");
      if (el) {
        const range = document.createRange();
        range.selectNodeContents(el);
        const sel = window.getSelection();
        sel?.removeAllRanges();
        sel?.addRange(range);
      }
    }
  };

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border)]">
        <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
          {title || "Raw JSON"}
        </span>
        <button
          onClick={handleCopy}
          className="text-[10px] px-2.5 py-1 rounded border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent-blue)]/40 transition-colors"
        >
          {copied ? "Copied!" : "Copy JSON"}
        </button>
      </div>
      {/* Content */}
      <pre
        id="json-viewer-pre"
        className="p-4 text-[11px] text-[var(--text-secondary)] overflow-x-auto max-h-[600px] overflow-y-auto font-mono leading-relaxed select-all"
      >
        {json}
      </pre>
    </div>
  );
}
