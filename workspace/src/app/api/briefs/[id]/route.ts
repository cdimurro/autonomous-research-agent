import { NextRequest, NextResponse } from "next/server";
import { getBrief } from "@/lib/backend";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const brief = await getBrief(id);
  if (!brief) {
    return NextResponse.json({ error: "Brief not found" }, { status: 404 });
  }
  return NextResponse.json({ brief });
}
