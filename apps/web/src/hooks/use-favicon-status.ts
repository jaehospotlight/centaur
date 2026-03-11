"use client";

import { useEffect, useRef } from "react";
import type { ThreadState } from "@/lib/types";

const FAVICON_RUNNING = `data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='12' fill='%2322c55e'/></svg>`;
const FAVICON_ERROR = `data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='12' fill='%23ef4444'/></svg>`;
const FAVICON_DONE = `data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='12' fill='%2322c55e'/><path d='M11 16l3 3 7-7' stroke='white' stroke-width='2.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>`;

function faviconForState(state: ThreadState | undefined): string | null {
  if (!state) return null;
  if (state === "running" || state === "working" || state === "stopping") return FAVICON_RUNNING;
  if (state === "error") return FAVICON_ERROR;
  if (state === "stopped") return FAVICON_DONE;
  return null;
}

export function useFaviconStatus(state: ThreadState | undefined) {
  const originalHrefRef = useRef<string | null>(null);
  const revertTimerRef = useRef<number>(0);

  useEffect(() => {
    const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!link) return;

    if (originalHrefRef.current === null) {
      originalHrefRef.current = link.href;
    }

    const favicon = faviconForState(state);
    if (favicon) {
      link.href = favicon;
    }

    if (state === "stopped" || state === "idle") {
      revertTimerRef.current = window.setTimeout(() => {
        if (originalHrefRef.current) {
          link.href = originalHrefRef.current;
        }
      }, 5000);
    }

    return () => {
      if (revertTimerRef.current) {
        window.clearTimeout(revertTimerRef.current);
      }
    };
  }, [state]);

  useEffect(() => {
    return () => {
      const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
      if (link && originalHrefRef.current) {
        link.href = originalHrefRef.current;
      }
    };
  }, []);
}
