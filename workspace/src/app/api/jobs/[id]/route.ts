import { NextRequest, NextResponse } from "next/server";
import { getJob, getJobLog } from "@/lib/backend";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const job = await getJob(id);
  if (!job) {
    return NextResponse.json({ error: "Job not found" }, { status: 404 });
  }
  const log = await getJobLog(id);
  return NextResponse.json({ job, log });
}
