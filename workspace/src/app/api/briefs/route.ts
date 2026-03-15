import { NextResponse } from "next/server";
import { listBriefs } from "@/lib/backend";

export async function GET() {
  const briefs = await listBriefs();
  return NextResponse.json({ briefs });
}
