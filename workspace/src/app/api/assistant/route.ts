import { NextRequest, NextResponse } from "next/server";
import { listBriefs } from "@/lib/backend";

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
- Summarize a validation run or decision brief
- Explain why a candidate was promoted or rejected
- Explain what a score component means
- Generate a founder-friendly summary
- Generate an investor-friendly summary
- Explain tradeoffs between candidates
- Suggest what to test next based on caveats`;

// DeepSeek API configuration
const DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
}

async function buildContext(): Promise<string> {
  // Load recent briefs for grounding
  const briefs = await listBriefs();
  if (briefs.length === 0) {
    return "\n[No decision briefs available yet. Guide the user to run a validation first.]";
  }

  const briefSummaries = briefs.slice(0, 5).map((b) => {
    return `- Brief ${b.id}: ${b.title || b.headline}
  Family: ${b.candidate_family}, Score: ${b.final_score}
  Confidence: ${b.confidence_tier}, Sidecar: ${b.sidecar_gate_decision}
  Caveats: ${(b.caveats as string[])?.join("; ") || "none"}
  Review: ${b.review_state}`;
  });

  return `\nAVAILABLE DATA (${briefs.length} total briefs, showing latest ${briefSummaries.length}):
${briefSummaries.join("\n")}`;
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const messages: Message[] = body.messages ?? [];
  const briefContext = body.brief_context ?? null;

  // Check for API key
  const apiKey = process.env.DEEPSEEK_API_KEY;
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
  let context = await buildContext();

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
