"use client";

import { useEffect, useRef, useState } from "react";

function normalizeStatus(value: string | null | undefined): string | null {
  const normalized = String(value ?? "").trim();
  return normalized ? normalized : null;
}

/**
 * Keeps status messages readable by enforcing a minimum display duration.
 * Rapid status updates are buffered and applied once the current message has
 * been visible long enough.
 */
export function useStableStatus(
  rawStatus: string | null | undefined,
  minDurationMs = 400,
): string | null {
  const normalizedRaw = normalizeStatus(rawStatus);
  const [stableStatus, setStableStatus] = useState<string | null>(normalizedRaw);
  const shownAtRef = useRef(Date.now());
  const stableRef = useRef<string | null>(normalizedRaw);
  const pendingRef = useRef<string | null>(null);

  useEffect(() => {
    stableRef.current = stableStatus;
  }, [stableStatus]);

  useEffect(() => {
    if (normalizedRaw === stableRef.current) {
      pendingRef.current = null;
      return;
    }

    const elapsed = Date.now() - shownAtRef.current;
    if (elapsed >= minDurationMs) {
      shownAtRef.current = Date.now();
      pendingRef.current = null;
      setStableStatus(normalizedRaw);
      return;
    }

    pendingRef.current = normalizedRaw;
    const timeout = window.setTimeout(() => {
      shownAtRef.current = Date.now();
      setStableStatus(pendingRef.current);
      pendingRef.current = null;
    }, minDurationMs - elapsed);

    return () => window.clearTimeout(timeout);
  }, [minDurationMs, normalizedRaw]);

  return stableStatus;
}
