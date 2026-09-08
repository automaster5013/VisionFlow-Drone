"use client";

import { useEffect, useState } from "react";
import { hasActivePresentation } from "@/lib/fleet-presentation-status";

export function useFleetPresentationSessions(droneIds: number[]) {
  const key = [...new Set(droneIds)].sort((a, b) => a - b).join(",");
  const [state, setState] = useState<{ key: string; active: Set<number>; failed: boolean }>({ key: "", active: new Set(), failed: false });
  useEffect(() => {
    const ids = key ? key.split(",").map(Number) : [];
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      const results = await Promise.all(ids.map(async id => {
        try {
          const response = await fetch(`/api/drones/${id}/flight-sessions?limit=20`, {
            cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8000)]),
          });
          if (!response.ok) throw new Error("Session lookup failed");
          const payload: unknown = await response.json();
          if (!Array.isArray(payload)) throw new Error("Invalid sessions");
          return { id, active: hasActivePresentation(payload, id), failed: false };
        } catch { return { id, active: false, failed: true }; }
      }));
      if (controller.signal.aborted) return;
      setState({ key, active: new Set(results.filter(r => r.active).map(r => r.id)), failed: results.some(r => r.failed) });
      timer = setTimeout(refresh, 5000);
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [key]);
  return { active: state.key === key ? state.active : new Set<number>(), failed: state.key === key && state.failed };
}
