"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import AssistantDrawer from "@/components/assistant/AssistantDrawer";
import AssistantToggle from "@/components/assistant/AssistantToggle";

export default function AssistantShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const [assistantOpen, setAssistantOpen] = useState(false);
  const pathname = usePathname();

  return (
    <>
      <main className="ml-56 min-h-screen">
        {children}
      </main>
      <AssistantDrawer
        isOpen={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        currentPage={pathname}
      />
      <AssistantToggle
        isOpen={assistantOpen}
        onToggle={() => setAssistantOpen(!assistantOpen)}
      />
    </>
  );
}
