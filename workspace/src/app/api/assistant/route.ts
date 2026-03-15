import { NextRequest, NextResponse } from "next/server";
import { listAllBriefs, getEnvVar } from "@/lib/backend";

const SYSTEM_PROMPT = `You are the Breakthrough Engine technical assistant.
You help users understand energy technology evaluation results, compare candidates,
and generate reports. You are task-oriented and grounded in data.

RULES:
- Base all answers on the structured data provided in context. Do not invent facts.
- If data is missing, say so clearly and suggest which workflow to run.
- When comparing candidates, use the score components, metrics, and caveats from the data.
- Keep answers concise and actionable.
- When asked to generate reports, format them clearly with sections.
- You can explain what scores mean, why candidates were promoted or rejected,
  and what tradeoffs exist.
- Never override or contradict the engine's canonical decisions.
- If the user asks about something outside the current data, guide them to
  the appropriate workflow (Validate, Research, or Due Diligence).

SUPPORTED TASKS:
- Compare battery materials or candidates
- Compare research directions or diligence findings
- Summarize a validation run, research brief, or diligence brief
- Explain why a candidate was promoted or rejected
- Explain what a score component means
- Generate a founder-friendly summary
- Generate an investor-friendly summary
- Explain tradeoffs between candidates
- Suggest what to test next based on caveats
- Create executive summaries across result types
- Explain risks and open questions from diligence briefs`;

const PAGE_CONTEXT_HINTS: Record<string, string> = {
  "/": "The user is on the Control Room (home) page. They can see recent jobs and briefs.",
  "/validate": "The user is on the Validate page. They are focused on benchmark validation results and candidate evaluation.",
  "/research": "The user is on the Research page. They are focused on research directions, promising paths, and rejected paths.",
  "/diligence": "The user is on the Due Diligence page. They are focused on technology assessment, signals, risks, and recommendations.",
  "/results": "The user is on the Results page. They can browse all briefs across types and compare them.",
};

// DeepSeek API configuration
const DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
}

async function buildContext(currentPage: string): Promise<string> {
  // Load all briefs for grounding
  const briefs = await listAllBriefs();
  if (briefs.length === 0) {
    return "\n[No briefs available yet. Guide the user to run a validation, research, or diligence workflow first.]";
  }

  // Separate by type
  const decisionBriefs = briefs.filter(
    (b) => !b.brief_type || b.brief_type === "decision"
  );
  const researchBriefs = briefs.filter((b) => b.brief_type === "research");
  const diligenceBriefs = briefs.filter((b) => b.brief_type === "diligence");

  const sections: string[] = [];

  // Decision briefs
  if (decisionBriefs.length > 0) {
    const summaries = decisionBriefs.slice(0, 5).map((b) => {
      return `  - ${b.id}: ${b.title || b.headline}
    Family: ${b.candidate_family}, Score: ${b.final_score}
    Confidence: ${b.confidence_tier}, Sidecar: ${b.sidecar_gate_decision}
    Caveats: ${(b.caveats as string[])?.join("; ") || "none"}
    Review: ${b.review_state}`;
    });
    sections.push(
      `DECISION BRIEFS (${decisionBriefs.length} total, showing ${summaries.length}):\n${summaries.join("\n")}`
    );
  }

  // Research briefs
  if (researchBriefs.length > 0) {
    const summaries = researchBriefs.slice(0, 3).map((b) => {
      const dirs = (b.promising_directions as Array<{ title: string }>)
        ?.map((d) => d.title)
        .join(", ");
      return `  - ${b.id}: ${b.headline}
    Topic: ${b.topic}, Domain: ${b.domain}
    Evidence: ${b.evidence_quality}
    Promising: ${dirs || "none"}
    Next: ${b.recommended_next}`;
    });
    sections.push(
      `RESEARCH BRIEFS (${researchBriefs.length} total, showing ${summaries.length}):\n${summaries.join("\n")}`
    );
  }

  // Diligence briefs
  if (diligenceBriefs.length > 0) {
    const summaries = diligenceBriefs.slice(0, 3).map((b) => {
      const risks = (b.risks as Array<{ title: string; severity: string }>)
        ?.map((r) => `${r.title} (${r.severity})`)
        .join(", ");
      return `  - ${b.id}: ${b.headline}
    Subject: ${b.subject}
    Focus: ${(b.focus_areas as string[])?.join(", ")}
    Risks: ${risks || "none identified"}
    Recommendation: ${b.recommendation}`;
    });
    sections.push(
      `DILIGENCE BRIEFS (${diligenceBriefs.length} total, showing ${summaries.length}):\n${summaries.join("\n")}`
    );
  }

  const pageHint = PAGE_CONTEXT_HINTS[currentPage] || "";

  return `\n${pageHint}\n\nAVAILABLE DATA:\n${sections.join("\n\n")}`;
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const messages: Message[] = body.messages ?? [];
  const briefContext = body.brief_context ?? null;
  const currentPage = body.current_page ?? "/";

  // Check for API key (try both naming conventions)
  const apiKey = getEnvVar("DEEPSEEK_API_KEY") || getEnvVar("DEEPSEEK_V3_API_KEY");
  if (!apiKey) {
    return NextResponse.json({
      response: {
        role: "assistant",
        content:
          "AI assistant is not configured. Set DEEPSEEK_API_KEY in workspace/.env.local to enable.\n\nFor now, you can inspect results directly on the Results page.",
      },
    });
  }

  // Build grounded context
  let context = await buildContext(currentPage);

  // If a specific brief is being discussed, include full data
  if (briefContext) {
    context += `\n\nCURRENTLY VIEWING BRIEF:\n${JSON.stringify(briefContext, null, 2)}`;
  }

  const systemMessage: Message = {
    role: "system",
    content: SYSTEM_PROMPT + context,
  };

  try {
    const res = await fetch(DEEPSEEK_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "deepseek-chat",
        messages: [systemMessage, ...messages],
        max_tokens: 2048,
        temperature: 0.3,
      }),
    });

    if (!res.ok) {
      const err = await res.text();
      return NextResponse.json(
        {
          response: {
            role: "assistant",
            content: `AI service error (${res.status}): ${err.slice(0, 200)}`,
          },
        },
        { status: 502 }
      );
    }

    const data = await res.json();
    const reply = data.choices?.[0]?.message;

    if (!reply) {
      return NextResponse.json(
        {
          response: {
            role: "assistant",
            content: "No response from AI service.",
          },
        },
        { status: 502 }
      );
    }

    return NextResponse.json({ response: reply });
  } catch (err) {
    return NextResponse.json(
      {
        response: {
          role: "assistant",
          content: `Failed to reach AI service: ${err instanceof Error ? err.message : "unknown error"}`,
        },
      },
      { status: 502 }
    );
  }
}
