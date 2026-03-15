"use client";

import { useState, useEffect, useCallback } from "react";

export function useBriefs() {
  const [briefs, setBriefs] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/briefs");
      if (res.ok) {
        const data = await res.json();
        setBriefs(data.briefs);
      }
    } catch {
      // Keep stale data on error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { briefs, loading, refresh };
}
