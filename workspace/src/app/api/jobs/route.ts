import { NextRequest, NextResponse } from "next/server";
import { listJobs, createJob, executeJob } from "@/lib/backend";
import type { JobType, ProductArea } from "@/lib/types";

const VALID_JOB_TYPES: JobType[] = [
  "battery_benchmark",
  "battery_validation",
  "pv_benchmark",
  "pv_validation",
  "research",
  "diligence",
];

const DOMAIN_MAP: Record<string, "battery" | "pv" | "general"> = {
  battery_benchmark: "battery",
  battery_validation: "battery",
  pv_benchmark: "pv",
  pv_validation: "pv",
  research: "general",
  diligence: "general",
};

const AREA_MAP: Record<string, ProductArea> = {
  battery_benchmark: "validate",
  battery_validation: "validate",
  pv_benchmark: "validate",
  pv_validation: "validate",
  research: "research",
  diligence: "diligence",
};

export async function GET() {
  const jobs = await listJobs();
  return NextResponse.json({ jobs });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const jobType = body.type as string;

  if (!VALID_JOB_TYPES.includes(jobType as JobType)) {
    return NextResponse.json(
      { error: `Invalid job type: ${jobType}` },
      { status: 400 }
    );
  }

  const type = jobType as JobType;

  // Research/diligence can specify a domain in config
  const configDomain = body.config?.domain as string | undefined;
  const domain =
    configDomain && (configDomain === "battery" || configDomain === "pv")
      ? configDomain
      : DOMAIN_MAP[type] ?? "general";

  const productArea = AREA_MAP[type] ?? "validate";
  const config = body.config ?? {};

  const job = await createJob(type, productArea, domain, config);

  // Execute in background — don't await
  executeJob(job.id).catch(() => {
    // Error already recorded in job file
  });

  return NextResponse.json({ job }, { status: 202 });
}
