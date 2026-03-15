"use client";

import { useState, useRef, useEffect } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const QUICK_TASKS = [
  "Summarize the latest validation run",
  "Compare the top two candidates",
  "Explain why this candidate was promoted",
  "Generate a founder-friendly summary",
  "Generate an investor-friendly summary",
  "What should we test next?",
];

export default function AssistantDrawer({
  isOpen,
  onClose,
  briefContext,
}: {
  isOpen: boolean;
  onClose: () => void;
  briefContext?: Record<string, unknown> | null;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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

  if (!isOpen) return null;

  return (
    <div className="fixed right-0 top-0 bottom-0 w-96 bg-[var(--bg-secondary)] border-l border-[var(--border)] z-40 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
        <div>
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            Assistant
          </h2>
          <p className="text-[10px] text-[var(--text-muted)]">
            Task-oriented &middot; grounded in results
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
                Quick Tasks
              </p>
              {QUICK_TASKS.map((task) => (
                <button
                  key={task}
                  onClick={() => sendMessage(task)}
                  className="block w-full text-left text-xs text-[var(--text-secondary)] px-3 py-2 rounded border border-[var(--border)] hover:border-[var(--accent-blue)]/40 hover:bg-[var(--bg-hover)] transition-colors"
                >
                  {task}
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
  );
}
