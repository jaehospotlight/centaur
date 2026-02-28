"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { timeAgo } from "@/lib/format";
import { ConsoleStream } from "@/components/thread/console-stream";
import { PhaseProgress } from "@/components/thread/phase-progress";
import { ReplyInput } from "@/components/thread/reply-input";
import { threadName } from "@/lib/thread-name";
import { useThreadStream } from "@/hooks/use-thread-stream";
import { HarnessBadge } from "@/components/ui/harness-badge";
import { StateDot } from "@/components/ui/state-dot";
import { BASE } from "@/lib/constants";

export default function ThreadDetailPage() {
  const params = useParams();
  const router = useRouter();
  const threadKey = decodeURIComponent(params.id as string);
  const { thread, error, fetchThread, isReconnecting } = useThreadStream(threadKey);
  const humanName = thread?.thread_name || threadName(threadKey);
  const [isInterrupting, setIsInterrupting] = useState(false);
  const [interruptError, setInterruptError] = useState<string | null>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (
          e.target instanceof HTMLElement &&
          e.target.closest("input, textarea, select, [contenteditable='true']")
        ) {
          return;
        }
        e.preventDefault();
        router.push("/threads");
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [router]);

  if (error && !thread) {
    return (
      <div className="h-[calc(100vh-41px)] flex items-center justify-center bg-zinc-950">
        <div className="text-center">
          <p className="text-red-400 text-sm mb-4">{error}</p>
          <div className="flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={fetchThread}
              className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer bg-transparent border border-zinc-800 rounded-md px-3 py-1"
            >
              Retry
            </button>
            <Link
              href="/threads"
              className="text-zinc-500 text-xs hover:text-zinc-300 transition-colors rounded-sm"
            >
              Back to threads
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!thread) {
    return (
      <div className="h-[calc(100vh-41px)] flex items-center justify-center bg-zinc-950">
        <div className="text-center">
          <p className="text-zinc-600 text-sm">Connecting…</p>
          <p className="text-zinc-700 text-xs font-mono mt-2">{threadName(threadKey)}</p>
        </div>
      </div>
    );
  }

  const isEngineer = thread.harness === "engineer";
  const isWaiting = thread.state === "waiting";
  const canInterrupt = !isEngineer && (thread.state === "working" || thread.state === "running");

  async function interruptRun() {
    if (!canInterrupt || isInterrupting) return;
    setInterruptError(null);
    setIsInterrupting(true);
    try {
      const res = await fetch(`${BASE}/api/agent/interrupt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slack_thread_key: threadKey }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data?.error) {
        const message =
          typeof data?.error === "string"
            ? data.error
            : `Interrupt failed${res.ok ? "" : ` (${res.status})`}.`;
        setInterruptError(message);
        return;
      }
      fetchThread();
    } finally {
      setIsInterrupting(false);
    }
  }

  return (
    <div className="h-[calc(100vh-41px)] flex flex-col bg-zinc-950 overflow-hidden">
      {/* Compact fixed header */}
      <div className="shrink-0 border-b border-zinc-800/50 bg-zinc-950">
        <div className="max-w-[960px] mx-auto px-5 py-3">
          <div className="flex items-center gap-2.5">
            <Link
              href="/threads"
              aria-label="Back to threads"
              className="text-zinc-600 text-xs hover:text-zinc-400 transition-colors mr-1 rounded-sm"
            >
              &larr;
            </Link>
            <HarnessBadge harness={thread.harness} />
            <StateDot state={thread.state} />
            <span className="text-xs text-zinc-500">{thread.state}</span>
            <span className="text-zinc-800 text-xs">|</span>
            <span className="text-[11px] text-zinc-300 font-medium truncate min-w-0">
              {humanName}
            </span>
            <span className="text-zinc-800 text-xs">|</span>
            <span className="text-[11px] text-zinc-600">
              {timeAgo(thread.last_activity)}
            </span>
            <span className="text-zinc-800 text-xs">|</span>
            <span className="text-[10px] text-zinc-700 font-mono truncate max-w-[200px]">
              {thread.slack_thread_key}
            </span>
            {thread.agent_thread_id && (
              <>
                <span className="text-zinc-800 text-xs">|</span>
                <span className="text-[10px] text-zinc-700 font-mono truncate max-w-[180px]">
                  {thread.agent_thread_id}
                </span>
              </>
            )}
            <span className="text-[10px] text-zinc-700 font-mono hidden sm:inline" title="Press Esc to go back">
              esc
            </span>
            {canInterrupt && (
              <button
                type="button"
                onClick={interruptRun}
                disabled={isInterrupting}
                className="text-[11px] text-red-400 hover:text-red-300 disabled:opacity-60 transition-colors cursor-pointer bg-transparent border-none p-0 rounded-sm"
              >
                {isInterrupting ? "Interrupting…" : "Interrupt"}
              </button>
            )}
            <button
              type="button"
              onClick={fetchThread}
              className="ml-auto text-zinc-600 text-[11px] hover:text-zinc-300 transition-colors cursor-pointer bg-transparent border-none p-0 rounded-sm"
            >
              Refresh
            </button>
          </div>
          {(() => {
            const showReconnect =
              isReconnecting && thread.state !== "error";
            const showError =
              !!error &&
              !(thread.state === "error" && error.startsWith("Stream disconnected."));
            return showError || !!interruptError || showReconnect;
          })() && (
            <div className="mt-2 text-[11px] text-amber-300">
              {interruptError ??
                (thread.state === "error" && error?.startsWith("Stream disconnected.")
                  ? null
                  : error) ??
                (isReconnecting ? "Reconnecting stream…" : "")}
            </div>
          )}

          {/* Phase progress (engineer only) */}
          {isEngineer && (thread.turns?.length ?? 0) > 0 && (
            <div className="mt-2">
              <PhaseProgress turns={thread.turns ?? []} />
            </div>
          )}
        </div>
      </div>

      {/* Console stream -- this is the only scrollable area */}
      <div className="flex-1 min-h-0 max-w-[960px] mx-auto w-full flex flex-col">
        <ConsoleStream turns={thread.turns ?? []} state={thread.state} />

        {/* Reply input (engineer waiting state) */}
        {isEngineer && isWaiting && (
          <div className="shrink-0 px-5 pb-3">
            <ReplyInput threadKey={thread.slack_thread_key} />
          </div>
        )}
      </div>
    </div>
  );
}
