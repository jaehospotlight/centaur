"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  CircleStop,
  Info,
  LoaderCircle,
  RefreshCw,
  Timer,
} from "lucide-react";
import { ActivityFeed } from "@/components/thread/activity-feed";
import { ParticipantAvatars } from "@/components/thread/participant-avatars";
import { PhaseProgress } from "@/components/thread/phase-progress";
import { ReplyInput } from "@/components/thread/reply-input";
import { threadName } from "@/lib/thread-name";
import { useThreadStream } from "@/hooks/use-thread-stream";
import { useElapsed } from "@/hooks/use-elapsed";
import { HarnessBadge } from "@/components/ui/harness-badge";
import { StateDot } from "@/components/ui/state-dot";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { BASE } from "@/lib/constants";

export default function ThreadDetailPage() {
  const params = useParams();
  const router = useRouter();
  const threadKey = decodeURIComponent(params.id as string);
  const {
    thread,
    error,
    fetchThread,
    isReconnecting,
    agentStatus,
    tokenUsage,
    chatStatus,
    sendReply,
    liveSteps,
  } = useThreadStream(threadKey);
  const humanName = thread?.thread_name || threadName(threadKey);
  const [isInterrupting, setIsInterrupting] = useState(false);
  const [interruptError, setInterruptError] = useState<string | null>(null);
  const isEngineer = thread?.harness === "engineer";
  const isWaiting = thread?.state === "waiting";
  const isRunning = thread?.state === "running" || thread?.state === "working";
  const canInterrupt = !!thread && !isEngineer && isRunning;
  const activeTurnStartedAt =
    thread && thread.turns.length > 0 ? thread.turns[thread.turns.length - 1]?.started_at : null;
  const elapsedAnchor = isRunning ? activeTurnStartedAt : thread?.last_activity;
  const liveElapsed = useElapsed(elapsedAnchor, Boolean(isRunning));
  const tokenTicker = tokenUsage
    ? `${tokenUsage.total_tokens.toLocaleString()} tok / ${
        tokenUsage.cost_usd === null ? "--" : `$${tokenUsage.cost_usd.toFixed(4)}`
      }${tokenUsage.estimated ? "~" : ""}`
    : "-- tok / --";
  const phases = liveSteps.flatMap((step) => (step.type === "phase" ? [step.phase] : []));

  const interruptRun = useCallback(async () => {
    if (!thread || !canInterrupt || isInterrupting) return;
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
  }, [canInterrupt, fetchThread, isInterrupting, thread, threadKey]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const targetIsInput =
        e.target instanceof HTMLElement &&
        e.target.closest("input, textarea, select, [contenteditable='true']");

      if (e.key === "Escape") {
        if (targetIsInput) {
          (e.target as HTMLElement | null)?.blur?.();
          return;
        }
        e.preventDefault();
        router.push("/threads");
        return;
      }

      if (targetIsInput) return;

      if (e.key.toLowerCase() === "r") {
        e.preventDefault();
        fetchThread();
        return;
      }

      if (e.key.toLowerCase() === "s" && canInterrupt) {
        e.preventDefault();
        if (!window.confirm("Stop the running agent for this thread?")) {
          return;
        }
        void interruptRun();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [canInterrupt, fetchThread, interruptRun, router]);

  useEffect(() => {
    if (!thread) return;
    const previousTitle = document.title;
    if (thread.state === "working" || thread.state === "running") {
      document.title = `● Working - ${humanName}`;
    } else if (thread.state === "waiting") {
      document.title = `⚠ Input needed - ${humanName}`;
    } else if (thread.state === "error") {
      document.title = `✗ Error - ${humanName}`;
    } else {
      document.title = `✓ Done - ${humanName}`;
    }
    return () => {
      document.title = previousTitle;
    };
  }, [humanName, thread]);

  if (error && !thread) {
    return (
      <div className="h-[calc(100vh-41px)] flex items-center justify-center bg-background">
        <div className="text-center">
          <p className="text-destructive text-sm mb-4">{error}</p>
          <div className="flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={fetchThread}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer bg-transparent border border-border rounded-sm px-3 py-1"
            >
              Retry
            </button>
            <Link
              href="/threads"
              className="text-muted-foreground text-xs hover:text-foreground transition-colors rounded-sm"
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
      <div className="h-[calc(100vh-41px)] flex items-center justify-center bg-background">
        <div className="text-center">
          <p className="text-muted-foreground text-sm inline-flex items-center gap-2">
            <LoaderCircle className="size-4 animate-spin text-primary" />
            Connecting…
          </p>
          <p className="text-muted-foreground text-xs font-mono mt-2">{threadName(threadKey)}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-41px)] flex flex-col bg-background overflow-hidden">
      {/* Compact fixed header */}
      <div className="shrink-0 border-b border-border bg-background">
        <div className="max-w-[960px] mx-auto px-5 py-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <Link
              href="/threads"
              aria-label="Back to threads"
              className="text-muted-foreground text-xs hover:text-foreground transition-colors mr-1 rounded-sm"
            >
              <ArrowLeft className="size-4" />
            </Link>
            <HarnessBadge harness={thread.harness} />
            <StateDot state={thread.state} />
            <span className="text-xs text-muted-foreground">{thread.state}</span>
            <span className="text-[11px] text-foreground font-medium truncate min-w-0">
              {humanName}
            </span>
            <ParticipantAvatars participants={thread.participants} size={20} />
            <span className="text-[11px] text-muted-foreground">
              {thread.turns.length} turn{thread.turns.length === 1 ? "" : "s"}
            </span>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-[11px] text-muted-foreground font-mono">{tokenTicker}</span>
              </TooltipTrigger>
              <TooltipContent>
                <div className="space-y-0.5 text-xs">
                  <div>Input: {tokenUsage?.input_tokens?.toLocaleString() ?? "--"}</div>
                  <div>Output: {tokenUsage?.output_tokens?.toLocaleString() ?? "--"}</div>
                  <div>Total: {tokenUsage?.total_tokens?.toLocaleString() ?? "--"}</div>
                  <div>Model: {tokenUsage?.model ?? "--"}</div>
                  <div>{tokenUsage?.authoritative ? "Authoritative usage" : "Usage unavailable"}</div>
                </div>
              </TooltipContent>
            </Tooltip>
            <span className="ml-auto text-[11px] text-muted-foreground inline-flex items-center gap-1">
              <Timer className="size-3.5" />
              {liveElapsed}
            </span>
            <span className="text-[10px] text-muted-foreground font-mono hidden sm:inline" title="Press Esc to go back">
              esc
            </span>
            <Popover>
              <PopoverTrigger asChild>
                <button
                  type="button"
                  className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  aria-label="Show thread metadata"
                >
                  <Info className="size-3.5" />
                </button>
              </PopoverTrigger>
              <PopoverContent className="w-[320px]">
                <div className="space-y-2 text-xs">
                  <div className="font-semibold text-foreground">Debug IDs</div>
                  <div className="font-mono text-muted-foreground break-all">{thread.slack_thread_key}</div>
                  {thread.agent_thread_id ? (
                    <div className="font-mono text-muted-foreground break-all">{thread.agent_thread_id}</div>
                  ) : null}
                </div>
              </PopoverContent>
            </Popover>
            {canInterrupt && (
              <button
                type="button"
                onClick={interruptRun}
                disabled={isInterrupting}
                className="inline-flex items-center gap-1 text-[11px] text-destructive hover:opacity-80 disabled:opacity-60 transition-colors cursor-pointer bg-transparent border-none p-0 rounded-sm"
              >
                <CircleStop className={isInterrupting ? "size-3.5 animate-pulse" : "size-3.5"} />
                {isInterrupting ? "Stopping…" : "Stop"}
              </button>
            )}
            <button
              type="button"
              onClick={fetchThread}
              className="text-muted-foreground text-[11px] hover:text-foreground transition-colors cursor-pointer bg-transparent border-none p-0 rounded-sm inline-flex items-center gap-1"
            >
              <RefreshCw className="size-3.5" />
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
            <div className="mt-2 text-[11px] text-amber-300 inline-flex items-center gap-1.5">
              <RefreshCw className={isReconnecting ? "size-3.5 animate-spin" : "size-3.5"} />
              {interruptError ??
                (thread.state === "error" && error?.startsWith("Stream disconnected.")
                  ? null
                  : error) ??
                (isReconnecting ? "Reconnecting stream…" : "")}
            </div>
          )}
          {chatStatus === "submitted" || chatStatus === "streaming" ? (
            <div className="mt-1 text-[11px] text-muted-foreground inline-flex items-center gap-1.5">
              <LoaderCircle className="size-3.5 animate-spin text-primary" />
              Live UI stream connected
            </div>
          ) : null}
          {agentStatus ? (
            <div className="mt-1 text-[11px] text-muted-foreground">{agentStatus}</div>
          ) : null}

          {/* Phase progress (engineer only) */}
          {isEngineer && phases.length > 0 && (
            <div className="mt-2">
              <PhaseProgress phases={phases} />
            </div>
          )}
        </div>
      </div>

      {/* Console stream -- this is the only scrollable area */}
      <div className="flex-1 min-h-0 max-w-[960px] mx-auto w-full flex flex-col">
        <ActivityFeed steps={liveSteps} state={thread.state} />

        {/* Reply input (engineer waiting state) */}
        {isEngineer && isWaiting && (
          <div className="shrink-0 px-5 pb-3">
            <ReplyInput threadKey={thread.slack_thread_key} onSend={sendReply} />
          </div>
        )}
      </div>
    </div>
  );
}
