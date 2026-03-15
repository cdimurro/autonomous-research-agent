"use client";

import { useState, useRef, useEffect, useCallback } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

// Page-specific quick tasks
const PAGE_TASKS: Record<string, Array<{ label: string; prompt: string }>> = {
  "/": [
    { label: "Summarize workspace status", prompt: "Summarize the current workspace status — what jobs have run recently, what briefs are available, and what should be done next." },
    { label: "What should I test next?", prompt: "Based on the available results and caveats, what should I test next?" },
    { label: "Create a founder-friendly summary", prompt: "Generate a founder-friendly summary of the latest results. Focus on what was validated, key findings, and recommended next steps." },
  ],
  "/validate": [
    { label: "Summarize latest validation", prompt: "Summarize the latest validation run — what was tested, what scored well, and what caveats exist." },
    { label: "Compare top two candidates", prompt: "Compare the top two decision briefs side by side. Highlight key differences in scores, caveats, and recommendations." },
    { label: "Explain promotion decision", prompt: "Explain why the most recent candidate was promoted or rejected. What factors were decisive?" },
    { label: "What tradeoffs exist?", prompt: "What tradeoffs exist between the most recent candidates? Focus on fast-charge vs degradation and sidecar verification." },
  ],
  "/research": [
    { label: "Summarize research findings", prompt: "Summarize the latest research briefs. What are the most promising directions and what was rejected?" },
    { label: "Compare research directions", prompt: "Compare the promising directions from the latest research briefs. Which has the highest confidence and why?" },
    { label: "Suggest next research topic", prompt: "Based on existing results and research briefs, suggest the next research topic that would be most valuable." },
  ],
  "/diligence": [
    { label: "Summarize diligence findings", prompt: "Summarize the latest diligence briefs. What are the strongest signals, key risks, and open questions?" },
    { label: "Create investor-facing summary", prompt: "Generate an investor-facing summary of the latest diligence findings. Focus on technical validation status, risk profile, and investment thesis support." },
    { label: "What risks need attention?", prompt: "What are the highest-severity risks from the latest diligence assessments? What should be investigated next?" },
  ],
  "/results": [
    { label: "Compare selected results", prompt: "Compare the available results. Highlight the most important differences and which result is strongest." },
    { label: "Explain recommendation", prompt: "Explain the recommendation from the latest result brief. What evidence supports it?" },
    { label: "Create executive summary", prompt: "Generate a concise executive summary of all available results for a non-technical audience." },
    { label: "Explain a rejection", prompt: "Explain why a recent candidate or direction was rejected. What factors led to the rejection?" },
  ],
};

const FALLBACK_TASKS = [
  { label: "Summarize latest validation run", prompt: "Summarize the latest validation run" },
  { label: "Compare top two candidates", prompt: "Compare the top two candidates" },
  { label: "Generate a founder-friendly summary", prompt: "Generate a founder-friendly summary" },
  { label: "What should we test next?", prompt: "What should we test next?" },
];

const PAGE_LABELS: Record<string, string> = {
  "/": "Control Room",
  "/validate": "Validate",
  "/research": "Research",
  "/diligence": "Due Diligence",
  "/results": "Results",
};

const MIN_WIDTH = 320;
const MAX_WIDTH = 900;
const DEFAULT_WIDTH = 420;

export default function AssistantDrawer({
  isOpen,
  onClose,
  briefContext,
  currentPage,
}: {
  isOpen: boolean;
  onClose: () => void;
  briefContext?: Record<string, unknown> | null;
  currentPage?: string;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Resize drag handling
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;

    const onMouseMove = (ev: MouseEvent) => {
      if (!dragging.current) return;
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, window.innerWidth - ev.clientX));
      setWidth(newWidth);
    };

    const onMouseUp = () => {
      dragging.current = false;
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, []);

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: Message = { role: "user", content: text.trim() };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: newMessages,
          brief_context: briefContext,
          current_page: currentPage || "/",
        }),
      });

      const data = await res.json();
      setMessages([
        ...newMessages,
        {
          role: "assistant",
          content:
            data.response?.content ?? "No response received.",
        },
      ]);
    } catch {
      setMessages([
        ...newMessages,
        {
          role: "assistant",
          content: "Failed to connect to the assistant service.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  // Get page-specific tasks
  const pageTasks = (currentPage && PAGE_TASKS[currentPage]) || FALLBACK_TASKS;
  const pageLabel = (currentPage && PAGE_LABELS[currentPage]) || "Workspace";

  if (!isOpen) return null;

  return (
    <div
      className="fixed right-0 top-0 bottom-0 bg-[var(--bg-secondary)] border-l border-[var(--border)] z-40 flex"
      style={{ width }}
    >
      {/* Resize handle */}
      <div
        onMouseDown={onMouseDown}
        className="w-1.5 cursor-col-resize hover:bg-[var(--accent-blue)]/30 active:bg-[var(--accent-blue)]/50 transition-colors shrink-0"
      />

      {/* Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
          <div>
            <h2 className="text-sm font-bold text-[var(--text-primary)]">
              Assistant
            </h2>
            <p className="text-[10px] text-[var(--text-muted)]">
              {pageLabel} &middot; grounded in results
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors text-lg leading-none"
          >
            &times;
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {messages.length === 0 && (
            <div className="space-y-3">
              <p className="text-xs text-[var(--text-muted)]">
                Ask about results, compare candidates, or generate reports.
                Answers are grounded in your latest engine outputs.
              </p>
              <div className="space-y-1.5">
                <p className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                  {pageLabel} Tasks
                </p>
                {pageTasks.map((task) => (
                  <button
                    key={task.label}
                    onClick={() => sendMessage(task.prompt)}
                    className="block w-full text-left text-xs text-[var(--text-secondary)] px-3 py-2 rounded border border-[var(--border)] hover:border-[var(--accent-blue)]/40 hover:bg-[var(--bg-hover)] transition-colors"
                  >
                    {task.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={`${
                msg.role === "user" ? "ml-8" : "mr-4"
              }`}
            >
              <div
                className={`rounded-lg px-3 py-2 text-xs leading-relaxed ${
                  msg.role === "user"
                    ? "bg-[var(--accent-blue)]/15 text-[var(--text-primary)]"
                    : "bg-[var(--bg-card)] text-[var(--text-secondary)]"
                }`}
              >
                <pre className="whitespace-pre-wrap font-[inherit]">
                  {msg.content}
                </pre>
              </div>
            </div>
          ))}

          {loading && (
            <div className="mr-4">
              <div className="rounded-lg px-3 py-2 bg-[var(--bg-card)]">
                <span className="text-xs text-[var(--text-muted)] animate-pulse">
                  Thinking...
                </span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="px-4 py-3 border-t border-[var(--border)]">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about results, compare candidates..."
              rows={2}
              className="flex-1 bg-[var(--bg-primary)] border border-[var(--border)] rounded px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]/50 resize-none"
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={loading || !input.trim()}
              className="px-3 py-2 bg-[var(--accent-blue)] text-white text-xs rounded hover:bg-[var(--accent-blue)]/80 transition-colors disabled:opacity-50 self-end"
            >
              Send
            </button>
          </div>
          <p className="text-[10px] text-[var(--text-muted)] mt-1.5">
            Grounded in engine outputs. Does not invent facts.
          </p>
        </div>
      </div>
    </div>
  );
}
