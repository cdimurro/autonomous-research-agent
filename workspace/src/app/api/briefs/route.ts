import { NextRequest, NextResponse } from "next/server";
import { listAllBriefs, listDecisionBriefs, listWorkspaceBriefs } from "@/lib/backend";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const typeFilter = searchParams.get("type"); // "decision" | "research" | "diligence" | null (all)

  let briefs;
  if (typeFilter === "decision") {
    briefs = await listDecisionBriefs();
  } else if (typeFilter === "research" || typeFilter === "diligence") {
    const ws = await listWorkspaceBriefs();
    briefs = ws.filter((b) => b.brief_type === typeFilter);
  } else {
    briefs = await listAllBriefs();
  }

  return NextResponse.json({ briefs });
}
