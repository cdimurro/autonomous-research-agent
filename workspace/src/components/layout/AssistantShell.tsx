"use client";

import { useState } from "react";
import AssistantDrawer from "@/components/assistant/AssistantDrawer";
import AssistantToggle from "@/components/assistant/AssistantToggle";

export default function AssistantShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const [assistantOpen, setAssistantOpen] = useState(false);

  return (
    <>
      <main
        className={`ml-56 min-h-screen transition-all duration-200 ${
          assistantOpen ? "mr-96" : ""
        }`}
      >
        {children}
      </main>
      <AssistantDrawer
        isOpen={assistantOpen}
        onClose={() => setAssistantOpen(false)}
      />
      <AssistantToggle
        isOpen={assistantOpen}
        onToggle={() => setAssistantOpen(!assistantOpen)}
      />
    </>
  );
}
