/**
 * Backend integration layer.
 *
 * Reads from the filesystem (runtime/ directory) and spawns Python CLI
 * processes for job execution. Research and diligence workflows use the
 * DeepSeek API to generate structured briefs grounded in engine data.
 *
 * This keeps the frontend thin — all source of truth remains in the
 * Python backend for science workflows.
 */

import { readdir, readFile, stat, writeFile, mkdir } from "fs/promises";
import { existsSync } from "fs";
import { join } from "path";
import { spawn } from "child_process";
import type {
  Job,
  JobType,
  ProductArea,
  ReviewState,
  ResearchBrief,
  DiligenceBrief,
  WorkspaceBrief,
} from "./types";

// Path to the repo root (workspace/ is one level deep)
const REPO_ROOT = join(process.cwd(), "..");
const ROOT_ENV_PATH = join(REPO_ROOT, ".env");

/**
 * Read a key from the repo root .env file.
 * Falls back to process.env (which includes workspace/.env.local via Next.js).
 */
export function getEnvVar(key: string): string | undefined {
  // Next.js .env.local takes priority
  if (process.env[key]) return process.env[key];
  // Fallback: read from repo root .env
  if (existsSync(ROOT_ENV_PATH)) {
    try {
      const content = require("fs").readFileSync(ROOT_ENV_PATH, "utf-8");
      for (const line of content.split("\n")) {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith("#")) {
          const eqIdx = trimmed.indexOf("=");
          if (eqIdx > 0) {
            const k = trimmed.slice(0, eqIdx).trim();
            if (k === key) {
              let val = trimmed.slice(eqIdx + 1).trim();
              if (
                (val.startsWith('"') && val.endsWith('"')) ||
                (val.startsWith("'") && val.endsWith("'"))
              ) {
                val = val.slice(1, -1);
              }
              return val;
            }
          }
        }
      }
    } catch {
      // Parse failure
    }
  }
  return undefined;
}

// Key directories
export const RUNTIME_DIR = join(REPO_ROOT, "runtime");
export const BRIEFS_DIR = join(RUNTIME_DIR, "battery_briefs");
export const EXPORTS_DIR = join(RUNTIME_DIR, "battery_exports");
export const EVAL_DIR = join(RUNTIME_DIR, "battery_eval");
export const LOOP_DIR = join(RUNTIME_DIR, "battery_loop");
export const PV_LOOP_DIR = join(RUNTIME_DIR, "pv_loop");
export const JOBS_DIR = join(RUNTIME_DIR, "workspace_jobs");
export const WORKSPACE_BRIEFS_DIR = join(RUNTIME_DIR, "workspace_briefs");
const PYTHON = join(REPO_ROOT, ".venv", "bin", "python");

// DeepSeek API
const DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions";

// ── Job management ──────────────────────────────────────────────────────

export async function ensureJobsDir(): Promise<void> {
  if (!existsSync(JOBS_DIR)) {
    await mkdir(JOBS_DIR, { recursive: true });
  }
}

async function ensureWorkspaceBriefsDir(): Promise<void> {
  if (!existsSync(WORKSPACE_BRIEFS_DIR)) {
    await mkdir(WORKSPACE_BRIEFS_DIR, { recursive: true });
  }
}

export async function createJob(
  type: JobType,
  productArea: ProductArea,
  domain: "battery" | "pv" | "general",
  config: Record<string, unknown>
): Promise<Job> {
  await ensureJobsDir();
  const id = `job_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const job: Job = {
    id,
    type,
    product_area: productArea,
    status: "queued",
    domain,
    config,
    created_at: new Date().toISOString(),
    started_at: null,
    completed_at: null,
    error: null,
    result_id: null,
  };
  await writeFile(
    join(JOBS_DIR, `${id}.json`),
    JSON.stringify(job, null, 2) + "\n"
  );
  return job;
}

export async function updateJob(
  id: string,
  updates: Partial<Job>
): Promise<Job> {
  const path = join(JOBS_DIR, `${id}.json`);
  const job: Job = JSON.parse(await readFile(path, "utf-8"));
  const updated = { ...job, ...updates };
  await writeFile(path, JSON.stringify(updated, null, 2) + "\n");
  return updated;
}

export async function getJob(id: string): Promise<Job | null> {
  const path = join(JOBS_DIR, `${id}.json`);
  if (!existsSync(path)) return null;
  return JSON.parse(await readFile(path, "utf-8"));
}

export async function listJobs(): Promise<Job[]> {
  await ensureJobsDir();
  const files = await readdir(JOBS_DIR);
  const jobs: Job[] = [];
  for (const f of files) {
    if (f.startsWith("job_") && f.endsWith(".json")) {
      try {
        const data = await readFile(join(JOBS_DIR, f), "utf-8");
        jobs.push(JSON.parse(data));
      } catch {
        // Skip malformed job files
      }
    }
  }
  // Sort newest first
  jobs.sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
  return jobs;
}

// ── Job execution (spawn Python CLI or AI workflow) ─────────────────────

function buildCommand(job: Job): { args: string[]; env: NodeJS.ProcessEnv } {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    PYTHONPATH: REPO_ROOT,
  };

  // Load .env vars if present
  const envPath = join(REPO_ROOT, ".env");
  if (existsSync(envPath)) {
    try {
      const envContent = require("fs").readFileSync(envPath, "utf-8");
      for (const line of envContent.split("\n")) {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith("#")) {
          const eqIdx = trimmed.indexOf("=");
          if (eqIdx > 0) {
            const key = trimmed.slice(0, eqIdx).trim();
            let val = trimmed.slice(eqIdx + 1).trim();
            // Strip surrounding quotes
            if (
              (val.startsWith('"') && val.endsWith('"')) ||
              (val.startsWith("'") && val.endsWith("'"))
            ) {
              val = val.slice(1, -1);
            }
            env[key] = val;
          }
        }
      }
    } catch {
      // .env parse failure — continue with process env
    }
  }

  const seed = job.config.seed as number | undefined;
  const mockSidecar = job.config.mock_sidecar as boolean | undefined;

  switch (job.type) {
    case "battery_benchmark": {
      const args = ["-m", "breakthrough_engine", "battery", "benchmark"];
      if (seed !== undefined) args.push("--seed", String(seed));
      if (mockSidecar) args.push("--mock-sidecar");
      return { args, env };
    }
    case "pv_benchmark": {
      const args = ["-m", "breakthrough_engine", "pv", "benchmark"];
      if (seed !== undefined) args.push("--seed", String(seed));
      return { args, env };
    }
    default:
      return { args: ["--version"], env };
  }
}

export async function executeJob(jobId: string): Promise<void> {
  const job = await getJob(jobId);
  if (!job) return;

  // Research and diligence jobs use AI workflow, not Python CLI
  if (job.type === "research") {
    return executeResearchJob(jobId, job);
  }
  if (job.type === "diligence") {
    return executeDiligenceJob(jobId, job);
  }

  await updateJob(jobId, {
    status: "running",
    started_at: new Date().toISOString(),
  });

  const { args, env } = buildCommand(job);

  return new Promise<void>((resolve) => {
    const proc = spawn(PYTHON, args, {
      cwd: REPO_ROOT,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data: Buffer) => {
      stdout += data.toString();
    });
    proc.stderr.on("data", (data: Buffer) => {
      stderr += data.toString();
    });

    proc.on("close", async (code) => {
      if (code === 0) {
        await updateJob(jobId, {
          status: "completed",
          completed_at: new Date().toISOString(),
        });
        // Post-processing: generate decision brief from battery benchmark
        if (job.type === "battery_benchmark") {
          try {
            await generateBriefFromBenchmark(job);
          } catch {
            // Non-critical: brief generation failure doesn't fail the job
          }
        }
      } else {
        await updateJob(jobId, {
          status: "failed",
          completed_at: new Date().toISOString(),
          error: stderr || `Process exited with code ${code}`,
        });
      }
      // Save output log
      try {
        await writeFile(
          join(JOBS_DIR, `${jobId}_output.log`),
          `=== STDOUT ===\n${stdout}\n\n=== STDERR ===\n${stderr}\n`
        );
      } catch {
        // Non-critical
      }
      resolve();
    });

    proc.on("error", async (err) => {
      await updateJob(jobId, {
        status: "failed",
        completed_at: new Date().toISOString(),
        error: `Spawn error: ${err.message}`,
      });
      resolve();
    });
  });
}

// ── Research job execution ──────────────────────────────────────────────

async function executeResearchJob(jobId: string, job: Job): Promise<void> {
  await updateJob(jobId, {
    status: "running",
    started_at: new Date().toISOString(),
  });

  const topic = (job.config.topic as string) || "general energy research";
  const domain = (job.config.domain as string) || "general";

  const apiKey =
    getEnvVar("DEEPSEEK_API_KEY") || getEnvVar("DEEPSEEK_V3_API_KEY");
  if (!apiKey) {
    await updateJob(jobId, {
      status: "failed",
      completed_at: new Date().toISOString(),
      error:
        "AI service not configured. Set DEEPSEEK_API_KEY in workspace/.env.local",
    });
    return;
  }

  try {
    // Gather grounding context from existing briefs
    const context = await buildGroundingContext(domain);

    const systemPrompt = `You are the Breakthrough Engine research analyst.
You produce structured research briefs for energy technology topics.
You are grounded in available engine data and never invent experimental results.

RULES:
- Base analysis on the provided context data when available.
- If evidence is weak or unavailable, say so explicitly.
- Generate 3-5 promising research directions with honest confidence levels.
- Generate 1-3 rejected or unpromising directions with clear reasons.
- Be specific about what makes each direction promising or not.
- Recommend a concrete next action.
- Rate overall evidence quality honestly.
- Include caveats about limitations of the analysis.

OUTPUT FORMAT: Respond with valid JSON matching this exact schema:
{
  "headline": "one-line summary of findings",
  "summary": "2-3 sentence overview",
  "promising_directions": [
    {"title": "...", "description": "...", "confidence": "high|medium|low", "rationale": "..."}
  ],
  "rejected_directions": [
    {"title": "...", "description": "...", "reason": "..."}
  ],
  "recommended_next": "specific next action",
  "evidence_quality": "strong|moderate|weak|insufficient",
  "caveats": ["caveat 1", "caveat 2"],
  "grounding_sources": ["source description 1"]
}

Respond ONLY with the JSON object. No markdown, no code fences.`;

    const userPrompt = `Research topic: ${topic}
Domain focus: ${domain}

${context}

Generate a structured research brief for this topic. Be honest about confidence levels and evidence quality.`;

    const res = await fetch(DEEPSEEK_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "deepseek-chat",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userPrompt },
        ],
        max_tokens: 4096,
        temperature: 0.4,
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`DeepSeek API error (${res.status}): ${errText.slice(0, 200)}`);
    }

    const data = await res.json();
    const rawContent = data.choices?.[0]?.message?.content ?? "";
    const parsed = parseJsonResponse(rawContent);

    const briefId = `research_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const brief: ResearchBrief = {
      id: briefId,
      brief_type: "research",
      created_at: new Date().toISOString(),
      topic,
      domain,
      headline: parsed.headline || "Research analysis complete",
      summary: parsed.summary || "",
      promising_directions: parsed.promising_directions || [],
      rejected_directions: parsed.rejected_directions || [],
      recommended_next: parsed.recommended_next || "",
      evidence_quality: parsed.evidence_quality || "insufficient",
      caveats: parsed.caveats || [],
      grounding_sources: parsed.grounding_sources || [],
      raw_analysis: rawContent,
      review_state: "awaiting_review",
      review_notes: "",
    };

    await ensureWorkspaceBriefsDir();
    await writeFile(
      join(WORKSPACE_BRIEFS_DIR, `brief_${briefId}.json`),
      JSON.stringify(brief, null, 2) + "\n"
    );

    await updateJob(jobId, {
      status: "completed",
      completed_at: new Date().toISOString(),
      result_id: briefId,
    });
  } catch (err) {
    await updateJob(jobId, {
      status: "failed",
      completed_at: new Date().toISOString(),
      error: err instanceof Error ? err.message : "Research job failed",
    });
  }
}

// ── Diligence job execution ─────────────────────────────────────────────

async function executeDiligenceJob(jobId: string, job: Job): Promise<void> {
  await updateJob(jobId, {
    status: "running",
    started_at: new Date().toISOString(),
  });

  const subject = (job.config.subject as string) || "energy technology";
  const focusAreas = (job.config.focus_areas as string[]) || [];
  const additionalContext = (job.config.additional_context as string) || "";

  const apiKey =
    getEnvVar("DEEPSEEK_API_KEY") || getEnvVar("DEEPSEEK_V3_API_KEY");
  if (!apiKey) {
    await updateJob(jobId, {
      status: "failed",
      completed_at: new Date().toISOString(),
      error:
        "AI service not configured. Set DEEPSEEK_API_KEY in workspace/.env.local",
    });
    return;
  }

  try {
    const context = await buildGroundingContext("general");

    const systemPrompt = `You are the Breakthrough Engine due diligence analyst.
You produce structured diligence briefs for energy technology assessments.
You are grounded in available engine data and never invent experimental results.

RULES:
- If technical validation data exists in the context, reference it explicitly.
- If market/competitive data is not available, state uncertainty clearly rather than guessing.
- Be honest about what can and cannot be assessed with available information.
- Identify strongest signals (positive, negative, or neutral) with supporting rationale.
- Identify risks with severity ratings.
- List open questions that need further investigation.
- Provide an honest recommendation.
- Include a confidence note explaining the basis and limitations of the assessment.

OUTPUT FORMAT: Respond with valid JSON matching this exact schema:
{
  "headline": "one-line assessment summary",
  "summary": "2-3 sentence overview",
  "strongest_signals": [
    {"title": "...", "description": "...", "signal_type": "positive|negative|neutral"}
  ],
  "risks": [
    {"title": "...", "description": "...", "severity": "high|medium|low"}
  ],
  "open_questions": ["question 1", "question 2"],
  "recommendation": "specific recommendation",
  "confidence_note": "explanation of assessment confidence and limitations",
  "caveats": ["caveat 1"],
  "grounding_sources": ["source description 1"]
}

Respond ONLY with the JSON object. No markdown, no code fences.`;

    const focusStr = focusAreas.length > 0 ? focusAreas.join(", ") : "general assessment";
    const userPrompt = `Due diligence subject: ${subject}
Focus areas: ${focusStr}
${additionalContext ? `Additional context: ${additionalContext}` : ""}

${context}

Generate a structured diligence brief. Be honest about confidence levels and what cannot be assessed with available data.`;

    const res = await fetch(DEEPSEEK_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "deepseek-chat",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userPrompt },
        ],
        max_tokens: 4096,
        temperature: 0.3,
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`DeepSeek API error (${res.status}): ${errText.slice(0, 200)}`);
    }

    const data = await res.json();
    const rawContent = data.choices?.[0]?.message?.content ?? "";
    const parsed = parseJsonResponse(rawContent);

    const briefId = `diligence_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const brief: DiligenceBrief = {
      id: briefId,
      brief_type: "diligence",
      created_at: new Date().toISOString(),
      subject,
      focus_areas: focusAreas,
      headline: parsed.headline || "Diligence assessment complete",
      summary: parsed.summary || "",
      strongest_signals: parsed.strongest_signals || [],
      risks: parsed.risks || [],
      open_questions: parsed.open_questions || [],
      recommendation: parsed.recommendation || "",
      confidence_note: parsed.confidence_note || "",
      caveats: parsed.caveats || [],
      grounding_sources: parsed.grounding_sources || [],
      raw_analysis: rawContent,
      review_state: "awaiting_review",
      review_notes: "",
    };

    await ensureWorkspaceBriefsDir();
    await writeFile(
      join(WORKSPACE_BRIEFS_DIR, `brief_${briefId}.json`),
      JSON.stringify(brief, null, 2) + "\n"
    );

    await updateJob(jobId, {
      status: "completed",
      completed_at: new Date().toISOString(),
      result_id: briefId,
    });
  } catch (err) {
    await updateJob(jobId, {
      status: "failed",
      completed_at: new Date().toISOString(),
      error: err instanceof Error ? err.message : "Diligence job failed",
    });
  }
}

// ── AI grounding context ────────────────────────────────────────────────

async function buildGroundingContext(domain: string): Promise<string> {
  const briefs = await listDecisionBriefs();
  if (briefs.length === 0) {
    return "AVAILABLE ENGINE DATA: No decision briefs or benchmark results available yet.";
  }

  const relevantBriefs = domain === "general"
    ? briefs.slice(0, 5)
    : briefs.filter((b) => {
        const bt = b.brief_type ?? "decision";
        if (bt === "decision") return domain === "battery" || domain === "pv";
        return true;
      }).slice(0, 5);

  if (relevantBriefs.length === 0) {
    return `AVAILABLE ENGINE DATA: No ${domain}-relevant results available.`;
  }

  const summaries = relevantBriefs.map((b) => {
    return `- ${b.title || b.headline}: Score ${b.final_score}, Family: ${b.candidate_family}, Confidence: ${b.confidence_tier}, Caveats: ${(b.caveats as string[])?.join("; ") || "none"}`;
  });

  return `AVAILABLE ENGINE DATA (${briefs.length} total decision briefs, showing ${summaries.length} relevant):
${summaries.join("\n")}`;
}

// ── JSON response parsing ───────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function parseJsonResponse(content: string): any {
  // Try direct parse first
  try {
    return JSON.parse(content);
  } catch {
    // Try extracting JSON from markdown code fences
    const fenceMatch = content.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
    if (fenceMatch) {
      try {
        return JSON.parse(fenceMatch[1]);
      } catch {
        // Fall through
      }
    }
    // Try finding first { ... } block
    const braceMatch = content.match(/\{[\s\S]*\}/);
    if (braceMatch) {
      try {
        return JSON.parse(braceMatch[0]);
      } catch {
        // Fall through
      }
    }
    return {};
  }
}

// ── Post-job processing ─────────────────────────────────────────────────

async function generateBriefFromBenchmark(job: Job): Promise<void> {
  const seed = job.config.seed ?? 42;
  const reportPath = join(LOOP_DIR, `battery_benchmark_${seed}.json`);
  if (!existsSync(reportPath)) return;

  // Call Python to generate and save the decision brief
  const script = `
import json, sys
sys.path.insert(0, "${REPO_ROOT}")
from breakthrough_engine.battery_decision_brief import generate_decision_brief, save_decision_brief
with open("${reportPath.replace(/\\/g, "/")}") as f:
    report = json.load(f)
brief = generate_decision_brief(report)
if brief:
    path = save_decision_brief(brief)
    print(f"Brief saved: {path}")
else:
    print("No candidate promoted — no brief generated")
`;

  return new Promise<void>((resolve) => {
    const proc = spawn(PYTHON, ["-c", script], {
      cwd: REPO_ROOT,
      env: { ...process.env, PYTHONPATH: REPO_ROOT },
      stdio: ["ignore", "pipe", "pipe"],
    });
    proc.on("close", () => resolve());
    proc.on("error", () => resolve());
  });
}

// ── Brief/artifact reading ──────────────────────────────────────────────

/** List decision briefs from battery_briefs/ and battery_exports/. */
export async function listDecisionBriefs(): Promise<Record<string, unknown>[]> {
  const briefs: Record<string, unknown>[] = [];
  const seen = new Set<string>();

  for (const dir of [BRIEFS_DIR, EXPORTS_DIR]) {
    if (!existsSync(dir)) continue;
    const files = await readdir(dir);
    for (const f of files) {
      if (f.startsWith("brief_") && f.endsWith(".json") && !f.includes("review")) {
        try {
          const data = await readFile(join(dir, f), "utf-8");
          const brief = JSON.parse(data);
          const briefId = brief.id as string;
          if (briefId && !seen.has(briefId)) {
            seen.add(briefId);
            // Tag with brief_type if missing
            if (!brief.brief_type) brief.brief_type = "decision";
            briefs.push(brief);
          }
        } catch {
          // Skip malformed
        }
      }
    }
  }

  briefs.sort((a, b) => {
    const ta = new Date(a.created_at as string).getTime();
    const tb = new Date(b.created_at as string).getTime();
    return tb - ta;
  });
  return briefs;
}

/** List research and diligence briefs from workspace_briefs/. */
export async function listWorkspaceBriefs(): Promise<Record<string, unknown>[]> {
  const briefs: Record<string, unknown>[] = [];
  if (!existsSync(WORKSPACE_BRIEFS_DIR)) return briefs;

  const files = await readdir(WORKSPACE_BRIEFS_DIR);
  for (const f of files) {
    if (f.startsWith("brief_") && f.endsWith(".json")) {
      try {
        const data = await readFile(join(WORKSPACE_BRIEFS_DIR, f), "utf-8");
        briefs.push(JSON.parse(data));
      } catch {
        // Skip malformed
      }
    }
  }

  briefs.sort((a, b) => {
    const ta = new Date(a.created_at as string).getTime();
    const tb = new Date(b.created_at as string).getTime();
    return tb - ta;
  });
  return briefs;
}

/** List all briefs across all types, sorted by creation date. */
export async function listAllBriefs(): Promise<Record<string, unknown>[]> {
  const [decision, workspace] = await Promise.all([
    listDecisionBriefs(),
    listWorkspaceBriefs(),
  ]);
  const all = [...decision, ...workspace];
  all.sort((a, b) => {
    const ta = new Date(a.created_at as string).getTime();
    const tb = new Date(b.created_at as string).getTime();
    return tb - ta;
  });
  return all;
}

/** Legacy alias for backward compatibility */
export const listBriefs = listDecisionBriefs;

export async function getBrief(
  briefId: string
): Promise<Record<string, unknown> | null> {
  // Check battery briefs first
  const batteryPath = join(BRIEFS_DIR, `brief_${briefId}.json`);
  if (existsSync(batteryPath)) {
    return JSON.parse(await readFile(batteryPath, "utf-8"));
  }
  // Check workspace briefs
  const wsPath = join(WORKSPACE_BRIEFS_DIR, `brief_${briefId}.json`);
  if (existsSync(wsPath)) {
    return JSON.parse(await readFile(wsPath, "utf-8"));
  }
  return null;
}

export async function listArtifacts(): Promise<
  Array<{ name: string; path: string; size: number; modified_at: string }>
> {
  const artifacts: Array<{
    name: string;
    path: string;
    size: number;
    modified_at: string;
  }> = [];

  const dirs = [BRIEFS_DIR, EXPORTS_DIR, EVAL_DIR, LOOP_DIR, PV_LOOP_DIR, WORKSPACE_BRIEFS_DIR];
  for (const dir of dirs) {
    if (!existsSync(dir)) continue;
    const files = await readdir(dir);
    for (const f of files) {
      if (f.endsWith(".json")) {
        try {
          const fpath = join(dir, f);
          const s = await stat(fpath);
          artifacts.push({
            name: f,
            path: fpath,
            size: s.size,
            modified_at: s.mtime.toISOString(),
          });
        } catch {
          // Skip inaccessible files
        }
      }
    }
  }

  artifacts.sort(
    (a, b) =>
      new Date(b.modified_at).getTime() - new Date(a.modified_at).getTime()
  );
  return artifacts;
}

// ── Brief review state updates ──────────────────────────────────────────

export async function updateBriefReview(
  briefId: string,
  reviewState: ReviewState,
  reviewNotes: string
): Promise<Record<string, unknown> | null> {
  // Try workspace briefs first (research/diligence)
  const wsPath = join(WORKSPACE_BRIEFS_DIR, `brief_${briefId}.json`);
  if (existsSync(wsPath)) {
    const brief = JSON.parse(await readFile(wsPath, "utf-8"));
    brief.review_state = reviewState;
    brief.review_notes = reviewNotes;
    await writeFile(wsPath, JSON.stringify(brief, null, 2) + "\n");
    return brief;
  }

  // For decision briefs, write a sidecar review file (don't modify Python-generated briefs)
  const batteryPath = join(BRIEFS_DIR, `brief_${briefId}.json`);
  if (existsSync(batteryPath)) {
    const brief = JSON.parse(await readFile(batteryPath, "utf-8"));
    brief.review_state = reviewState;
    brief.review_notes = reviewNotes;
    // Write updated brief back (decision briefs already have review_state)
    await writeFile(batteryPath, JSON.stringify(brief, null, 2) + "\n");
    return brief;
  }

  return null;
}

// ── Job log reading ─────────────────────────────────────────────────────

export async function getJobLog(jobId: string): Promise<string | null> {
  const logPath = join(JOBS_DIR, `${jobId}_output.log`);
  if (!existsSync(logPath)) return null;
  return readFile(logPath, "utf-8");
}

export async function readArtifact(
  artifactPath: string
): Promise<string | null> {
  // Security: only allow reading from runtime/ directory
  const resolved = require("path").resolve(artifactPath);
  if (!resolved.startsWith(RUNTIME_DIR)) return null;
  if (!existsSync(resolved)) return null;
  return readFile(resolved, "utf-8");
}
