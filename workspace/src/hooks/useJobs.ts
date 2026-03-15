"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { Job } from "@/lib/types";

export function useJobs(pollIntervalMs = 5000) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  // Track IDs that transitioned to completed/failed since last check
  const [recentCompletions, setRecentCompletions] = useState<string[]>([]);
  const prevJobsRef = useRef<Map<string, string>>(new Map());

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/jobs");
      if (res.ok) {
        const data = await res.json();
        const newJobs = data.jobs as Job[];

        // Detect jobs that just completed or failed
        const newCompletions: string[] = [];
        for (const job of newJobs) {
          const prevStatus = prevJobsRef.current.get(job.id);
          if (
            prevStatus &&
            (prevStatus === "running" || prevStatus === "queued") &&
            (job.status === "completed" || job.status === "failed")
          ) {
            newCompletions.push(job.id);
          }
        }

        // Update previous state map
        const nextMap = new Map<string, string>();
        for (const job of newJobs) {
          nextMap.set(job.id, job.status);
        }
        prevJobsRef.current = nextMap;

        if (newCompletions.length > 0) {
          setRecentCompletions(newCompletions);
        }

        setJobs(newJobs);
      }
    } catch {
      // Network error — keep stale data
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, pollIntervalMs);
    return () => clearInterval(timer);
  }, [refresh, pollIntervalMs]);

  const submitJob = useCallback(
    async (type: string, config: Record<string, unknown> = {}) => {
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, config }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || "Failed to submit job");
      }
      const data = await res.json();
      // Immediately refresh to show the new job
      await refresh();
      return data.job as Job;
    },
    [refresh]
  );

  // Allow consumers to acknowledge completions
  const clearCompletions = useCallback(() => {
    setRecentCompletions([]);
  }, []);

  const hasActiveJobs = jobs.some(
    (j) => j.status === "running" || j.status === "queued"
  );

  return {
    jobs,
    loading,
    refresh,
    submitJob,
    recentCompletions,
    clearCompletions,
    hasActiveJobs,
  };
}
