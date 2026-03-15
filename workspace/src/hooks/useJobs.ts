"use client";

import { useState, useEffect, useCallback } from "react";
import type { Job } from "@/lib/types";

export function useJobs(pollIntervalMs = 5000) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/jobs");
      if (res.ok) {
        const data = await res.json();
        setJobs(data.jobs);
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

  return { jobs, loading, refresh, submitJob };
}
