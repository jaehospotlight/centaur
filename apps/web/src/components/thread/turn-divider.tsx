"use client";

import { useEffect, useMemo, useState } from "react";

function formatRelativeTime(timestamp: string | null | undefined, nowMs: number): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return "";
  const diffMs = nowMs - date.getTime();
  const diffS = Math.floor(diffMs / 1000);
  const diffM = Math.floor(diffS / 60);
  const diffH = Math.floor(diffM / 60);
  const diffD = Math.floor(diffH / 24);

  if (diffS < 60) return "Just now";
  if (diffM < 60) return `${diffM} minute${diffM === 1 ? "" : "s"} ago`;
  if (diffH < 24) return `${diffH} hour${diffH === 1 ? "" : "s"} ago`;
  if (diffD < 7) return `${diffD} day${diffD === 1 ? "" : "s"} ago`;

  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function TurnDivider({ timestamp }: { timestamp?: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const label = useMemo(() => formatRelativeTime(timestamp, now), [timestamp, now]);

  return (
    <div className="flex items-center gap-3 px-2 py-1" role="separator">
      <div className="h-px flex-1 bg-border/40" />
      <span className="shrink-0 text-xs text-muted-foreground/60">{label || "New turn"}</span>
      <div className="h-px flex-1 bg-border/40" />
    </div>
  );
}
