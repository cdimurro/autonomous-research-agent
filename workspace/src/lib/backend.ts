/**
 * Backend integration layer.
 *
 * Reads from the filesystem (runtime/ directory) and spawns Python CLI
 * processes for job execution. This keeps the frontend thin — all source
 * of truth remains in the Python backend.
 */

import { readdir, readFile, stat, writeFile, mkdir } from "fs/promises";
import { existsSync } from "fs";
import { join } from "path";
import { spawn } from "child_process";
import type { Job, JobStatus, JobType, ProductArea } from "./types";

// Path to the repo root (workspace/ is one level deep)
const REPO_ROOT = join(process.cwd(), "..");

// Key directories
export const RUNTIME_DIR = join(REPO_ROOT, "runtime");
export const BRIEFS_DIR = join(RUNTIME_DIR, "battery_briefs");
export const EXPORTS_DIR = join(RUNTIME_DIR, "battery_exports");
export const EVAL_DIR = join(RUNTIME_DIR, "battery_eval");
export const JOBS_DIR = join(RUNTIME_DIR, "workspace_jobs");
const PYTHON = join(REPO_ROOT, ".venv", "bin", "python");

// ── Job management ──────────────────────────────────────────────────────

export async function ensureJobsDir(): Promise<void> {
  if (!existsSync(JOBS_DIR)) {
    await mkdir(JOBS_DIR, { recursive: true });
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

// ── Job execution (spawn Python CLI) ────────────────────────────────────

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

// ── Brief/artifact reading ──────────────────────────────────────────────

export async function listBriefs(): Promise<Record<string, unknown>[]> {
  if (!existsSync(BRIEFS_DIR)) return [];
  const files = await readdir(BRIEFS_DIR);
  const briefs: Record<string, unknown>[] = [];
  for (const f of files) {
    if (f.startsWith("brief_") && f.endsWith(".json")) {
      try {
        const data = await readFile(join(BRIEFS_DIR, f), "utf-8");
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

export async function getBrief(
  briefId: string
): Promise<Record<string, unknown> | null> {
  const path = join(BRIEFS_DIR, `brief_${briefId}.json`);
  if (!existsSync(path)) return null;
  return JSON.parse(await readFile(path, "utf-8"));
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

  const dirs = [BRIEFS_DIR, EXPORTS_DIR, EVAL_DIR];
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

export async function readArtifact(
  artifactPath: string
): Promise<string | null> {
  // Security: only allow reading from runtime/ directory
  const resolved = require("path").resolve(artifactPath);
  if (!resolved.startsWith(RUNTIME_DIR)) return null;
  if (!existsSync(resolved)) return null;
  return readFile(resolved, "utf-8");
}
