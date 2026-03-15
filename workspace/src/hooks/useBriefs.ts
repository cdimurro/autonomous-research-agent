"use client";

import { useState, useEffect, useCallback } from "react";
import type { BriefType } from "@/lib/types";

export function useBriefs(typeFilter?: BriefType, pollIntervalMs?: number) {
  const [briefs, setBriefs] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const params = typeFilter ? `?type=${typeFilter}` : "";
      const res = await fetch(`/api/briefs${params}`);
      if (res.ok) {
        const data = await res.json();
        setBriefs(data.briefs);
      }
    } catch {
      // Keep stale data on error
    } finally {
      setLoading(false);
    }
  }, [typeFilter]);

  useEffect(() => {
    refresh();
    if (pollIntervalMs && pollIntervalMs > 0) {
      const timer = setInterval(refresh, pollIntervalMs);
      return () => clearInterval(timer);
    }
  }, [refresh, pollIntervalMs]);

  return { briefs, loading, refresh };
}
