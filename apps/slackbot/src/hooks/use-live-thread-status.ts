"use client";

import { useEffect, useMemo, useState } from "react";
import { BASE } from "@/lib/constants";

export function useLiveThreadStatus(threadKeys: string[]) {
  const [statusByThread, setStatusByThread] = useState<Record<string, string>>({});
  const normalizedKeySignature = useMemo(() => [...new Set(threadKeys)].sort().join("|"), [threadKeys]);
  const normalizedKeys = useMemo(
    () => (normalizedKeySignature ? normalizedKeySignature.split("|") : []),
    [normalizedKeySignature],
  );

  useEffect(() => {
    const activeKeys = new Set(normalizedKeys);
    setStatusByThread((current) => {
      let changed = false;
      const next: Record<string, string> = {};
      for (const [key, value] of Object.entries(current)) {
        if (activeKeys.has(key)) {
          next[key] = value;
          continue;
        }
        changed = true;
      }
      return changed ? next : current;
    });

    if (normalizedKeys.length === 0) {
      setStatusByThread({});
      return;
    }

    const streams: EventSource[] = [];

    for (const key of normalizedKeys) {
      const es = new EventSource(
        `${BASE}/api/threads/stream-ui?key=${encodeURIComponent(key)}&live_only=1`,
      );
      streams.push(es);
      es.onmessage = (event) => {
        if (!event.data || event.data === "[DONE]") return;
        try {
          const chunk = JSON.parse(event.data) as {
            type?: string;
            data?: { text?: string };
          };
          if (chunk.type === "data-agent-status") {
            const text = String(chunk.data?.text ?? "").trim();
            setStatusByThread((current) => {
              if (!text) {
                if (!(key in current)) return current;
                const next = { ...current };
                delete next[key];
                return next;
              }
              return { ...current, [key]: text };
            });
          }
          if (chunk.type === "finish") {
            setStatusByThread((current) => {
              if (!(key in current)) return current;
              const next = { ...current };
              delete next[key];
              return next;
            });
          }
        } catch {
          // Ignore malformed chunks.
        }
      };
      // EventSource reconnects automatically on transient network failures.
      es.onerror = () => {};
    }

    return () => {
      for (const es of streams) es.close();
    };
  }, [normalizedKeySignature]);

  return statusByThread;
}
