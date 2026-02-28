import { useEffect, useMemo, useState } from "react";
import { timeAgo } from "@/lib/format";

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

export function useElapsed(startedAt: number | null | undefined, isRunning: boolean): string {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!isRunning || !startedAt) return;
    const interval = setInterval(() => setTick((value) => value + 1), 1000);
    return () => clearInterval(interval);
  }, [isRunning, startedAt]);

  return useMemo(() => {
    if (!startedAt || !Number.isFinite(startedAt)) return "unknown";
    if (!isRunning) return timeAgo(startedAt);
    const nowSeconds = Math.floor(Date.now() / 1000);
    const elapsed = Math.max(0, nowSeconds - Math.floor(startedAt));
    return formatElapsed(elapsed);
  }, [isRunning, startedAt, tick]);
}
