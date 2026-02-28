"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ThreadSummary } from "@/lib/types";
import { timeAgo } from "@/lib/format";
import { BASE } from "@/lib/constants";
import { threadName } from "@/lib/thread-name";
import { HarnessBadge } from "@/components/ui/harness-badge";
import { StateDot } from "@/components/ui/state-dot";

export default function ThreadsPage() {
  const router = useRouter();
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchThreads = useCallback(async (showRefreshIndicator = true) => {
    if (showRefreshIndicator) setIsRefreshing(true);
    try {
      const res = await fetch(`${BASE}/api/threads`);
      if (!res.ok) {
        throw new Error(`threads fetch failed: ${res.status}`);
      }
      const data = await res.json();
      setThreads(data.threads || []);
      setError(null);
    } catch {
      setError("Unable to load threads.");
    } finally {
      setLoading(false);
      if (showRefreshIndicator) setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchThreads(false);
    const interval = setInterval(() => fetchThreads(false), 5000);
    return () => clearInterval(interval);
  }, [fetchThreads]);

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-200 font-sans px-8 py-8 max-w-[1200px] mx-auto">
      <div className="flex justify-between items-center mb-6 pb-4 border-b border-zinc-800/50">
        <div>
          <h1 className="text-base font-semibold text-zinc-50 tracking-tight">
            Threads
          </h1>
          <p className="text-xs text-zinc-600 mt-0.5">
            {`${threads.length} active agent${threads.length !== 1 ? "s" : ""}`}
          </p>
        </div>
        <button
          type="button"
          onClick={() => fetchThreads(true)}
          disabled={isRefreshing}
          aria-busy={isRefreshing}
          className="bg-transparent border border-zinc-800 rounded-md text-zinc-500 px-3 py-1 text-xs font-medium cursor-pointer hover:border-zinc-600 hover:text-zinc-200 transition-colors disabled:opacity-60 disabled:cursor-default"
        >
          {isRefreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {loading ? (
        <p className="text-zinc-700 text-center py-16 text-sm">Loading…</p>
      ) : error && threads.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-red-400 text-sm mb-3">{error}</p>
          <button
            type="button"
            onClick={() => fetchThreads(true)}
            className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer bg-transparent border border-zinc-800 rounded-md px-3 py-1"
          >
            Retry
          </button>
        </div>
      ) : threads.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-zinc-600 text-sm font-medium mb-1">
            No active agent threads
          </p>
          <p className="text-zinc-700 text-xs">
            Mention @paradigm-ai in a Slack thread to start one
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(360px,1fr))] gap-2.5">
          {threads.map((t) => {
            const name = t.thread_name || threadName(t.slack_thread_key);
            const href = `/threads/${encodeURIComponent(t.slack_thread_key)}`;
            const rawTask = t.first_message || t.last_result || "";
            const taskPreview = rawTask.replace(/^\[[\w]+\]\s*/, "").slice(0, 100);

            return (
              <Link
                key={t.slack_thread_key}
                href={href}
                prefetch={false}
                onMouseEnter={() => router.prefetch(href)}
                aria-label={`View thread ${name}, ${t.state}, ${t.turn_count} turns`}
                className="block bg-surface border border-zinc-800/50 rounded-lg p-4 no-underline text-inherit hover:border-zinc-600 hover:bg-zinc-800/30 transition-colors"
              >
                <div className="flex items-center justify-between mb-2 min-w-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <HarnessBadge harness={t.harness} />
                    <span className="text-sm text-zinc-200 font-medium truncate">
                      {name}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <StateDot state={t.state} />
                    <span className="text-[11px] text-zinc-600">
                      {t.state}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 text-[11px] text-zinc-600 mb-1.5">
                  <span>
                    {t.turn_count} turn{t.turn_count !== 1 ? "s" : ""}
                  </span>
                  <span className="text-zinc-800">·</span>
                  <span>{timeAgo(t.last_activity)}</span>
                  <span className="text-zinc-800">·</span>
                  <span className="font-mono text-zinc-700 truncate">
                    {t.slack_thread_key.split(":")[0]}
                  </span>
                </div>

                {taskPreview && (
                  <div className="text-xs text-zinc-600 leading-relaxed line-clamp-1 mt-1">
                    {taskPreview}
                  </div>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </main>
  );
}
