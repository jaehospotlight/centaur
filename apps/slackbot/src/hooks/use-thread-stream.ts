import { useState, useCallback, useRef, useEffect, startTransition } from "react";
import type { ThreadDetail } from "@/lib/types";
import { BASE } from "@/lib/constants";

export function useThreadStream(threadKey: string) {
  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchThread = useCallback(async () => {
    try {
      const res = await fetch(
        `${BASE}/api/threads/detail?key=${encodeURIComponent(threadKey)}`
      );
      if (!res.ok) {
        startTransition(() => {
          setThread(null);
          setError(`Thread not found: ${threadKey}`);
        });
        return;
      }
      const data = await res.json();
      if (data.error) {
        startTransition(() => {
          setThread(null);
          setError(data.error);
        });
        return;
      }
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      startTransition(() => {
        setIsReconnecting(false);
        setThread(data);
        setError(null);
      });
    } catch {
      startTransition(() => {
        setThread(null);
        setError("Failed to fetch thread");
      });
    }
  }, [threadKey]);

  useEffect(() => {
    setThread(null);
    setError(null);
    setIsReconnecting(false);
    fetchThread();

    const url = `${BASE}/api/threads/stream?key=${encodeURIComponent(threadKey)}`;
    let es: EventSource | null = null;
    let retryCount = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    function scheduleReconnect() {
      const delay = Math.min(1000 * 2 ** retryCount, 10000);
      retryCount++;
      retryTimer = setTimeout(connect, delay);
    }

    function connect() {
      if (stopped) return;
      es = new EventSource(url);
      let connected = false;

      es.onmessage = (event) => {
        connected = true;
        retryCount = 0;
        try {
          const data = JSON.parse(event.data);
          if (data.error) {
            es?.close();
            startTransition(() => {
              setThread(null);
              setError(
                data.error === "not_found"
                  ? `Thread not found: ${threadKey}`
                  : String(data.error)
              );
            });
            if (!pollingRef.current) {
              pollingRef.current = setInterval(fetchThread, 3000);
            }
            return;
          }
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
          startTransition(() => {
            setIsReconnecting(false);
            setThread(data);
            setError(null);
          });
        } catch {
          startTransition(() => {
            setThread(null);
            setError("Malformed stream payload");
          });
        }
      };

      es.onerror = () => {
        es?.close();
        if (stopped) return;
        if (!connected) {
          startTransition(() => {
            setIsReconnecting(true);
            setError("Connection lost. Falling back to polling...");
          });
          if (!pollingRef.current) {
            pollingRef.current = setInterval(fetchThread, 3000);
          }
          scheduleReconnect();
          return;
        }
        startTransition(() => {
          setIsReconnecting(true);
          setError("Stream disconnected. Reconnecting...");
        });
        scheduleReconnect();
      };
    }

    connect();

    return () => {
      stopped = true;
      es?.close();
      if (retryTimer) clearTimeout(retryTimer);
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [threadKey, fetchThread]);

  return { thread, error, fetchThread, isReconnecting };
}
