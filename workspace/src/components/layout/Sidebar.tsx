"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Home", icon: "H" },
  { href: "/validate", label: "Validate", icon: "V" },
  { href: "/research", label: "Research", icon: "R" },
  { href: "/diligence", label: "Due Diligence", icon: "D" },
  { href: "/results", label: "Results", icon: ">" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-56 bg-[var(--bg-secondary)] border-r border-[var(--border)] flex flex-col z-30">
      {/* Logo / Brand */}
      <div className="px-4 py-5 border-b border-[var(--border)]">
        <h1 className="text-sm font-bold tracking-wide text-[var(--text-primary)]">
          BREAKTHROUGH
        </h1>
        <p className="text-[10px] text-[var(--text-muted)] mt-0.5 tracking-widest uppercase">
          Dev Workspace
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon }) => {
          const isActive =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
                isActive
                  ? "bg-[var(--accent-blue)]/15 text-[var(--accent-blue)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
              }`}
            >
              <span
                className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold ${
                  isActive
                    ? "bg-[var(--accent-blue)]/20 text-[var(--accent-blue)]"
                    : "bg-[var(--bg-card)] text-[var(--text-muted)]"
                }`}
              >
                {icon}
              </span>
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-[var(--border)] text-[10px] text-[var(--text-muted)]">
        <p>v0.1.0 &middot; internal</p>
      </div>
    </aside>
  );
}
