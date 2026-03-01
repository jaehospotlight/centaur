"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useParams, useRouter } from "next/navigation";
import { CircleStop, Info, LoaderCircle, Menu, RefreshCw, Timer } from "lucide-react";
import { useHotkeys } from "react-hotkeys-hook";
import { ActivityFeed } from "@/components/thread/activity-feed";
import { CommandSurfaceIcon, CompactDensityIcon } from "@/components/thread/icons/thread-icons";
import { MessageInput } from "@/components/thread/message-input";
import { ParticipantAvatars } from "@/components/thread/participant-avatars";
import { PhaseProgress } from "@/components/thread/phase-progress";
import { StatusBar } from "@/components/thread/status-bar";
import { threadName } from "@/lib/thread-name";
import { useThreadStream } from "@/hooks/use-thread-stream";
import { useStableStatus } from "@/hooks/use-stable-status";
import { useElapsed } from "@/hooks/use-elapsed";
import { HarnessBadge } from "@/components/ui/harness-badge";
import { StateDot } from "@/components/ui/state-dot";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { BASE } from "@/lib/constants";
import type { ThreadSummary } from "@/lib/types";

const COMPACT_MODE_STORAGE_KEY = "thread-viewer:compact-mode";
const PALETTE_REFRESH_INTERVAL_MS = 15000;
const CommandPalette = dynamic(
  () => import("@/components/thread/command-palette").then((module) => module.CommandPalette),
  { ssr: false },
);

function isEditableTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && !!target.closest("input, textarea, select, [contenteditable='true']");
}

function slackUrlForThread(threadKey: string): string | null {
  const [channel, messageTs] = threadKey.split(":");
  if (!channel || !messageTs || !messageTs.includes(".")) return null;
  return `https://slack.com/app_redirect?channel=${encodeURIComponent(channel)}&message_ts=${encodeURIComponent(messageTs)}`;
}

function ShortcutHelpDialog({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-sm border border-border bg-card p-4 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Keyboard Shortcuts</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-sm border border-border px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            Close
          </button>
        </div>
        <div className="space-y-2 text-xs text-muted-foreground">
          <div className="flex items-center justify-between">
            <span>Open command palette</span>
            <span className="font-mono">Cmd/Ctrl+K</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Toggle compact mode</span>
            <span className="font-mono">Cmd/Ctrl+.</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Refresh thread</span>
            <span className="font-mono">R</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Stop agent</span>
            <span className="font-mono">S</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Send message</span>
            <span className="font-mono">Cmd/Ctrl+Enter</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Show this help</span>
            <span className="font-mono">Shift+?</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Focus search</span>
            <span className="font-mono">/</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Back to threads</span>
            <span className="font-mono">Esc</span>
          </div>
        </div>
      </div>
    </div>
  );
}

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
    sendThreadMessage,
    interruptThread,
    liveSteps,
  } = useThreadStream(threadKey);
  const humanName = thread?.thread_name || threadName(threadKey);
  const [isInterrupting, setIsInterrupting] = useState(false);
  const [interruptError, setInterruptError] = useState<string | null>(null);
  const [compactMode, setCompactMode] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [showShortcutHelp, setShowShortcutHelp] = useState(false);
  const [paletteThreads, setPaletteThreads] = useState<ThreadSummary[]>([]);
  const [paletteLoadedAt, setPaletteLoadedAt] = useState(0);
  const [isPaletteLoading, setIsPaletteLoading] = useState(false);
  const isEngineer = thread?.harness === "engineer";
  const isWaiting = thread?.state === "waiting";
  const isRunning = thread?.state === "running" || thread?.state === "working";
  const hasStreamingConnection = chatStatus === "submitted" || chatStatus === "streaming";
  const isAgentRunning = isRunning || hasStreamingConnection;
  const canInterrupt = !!thread && isAgentRunning;
  const activeTurnStartedAt =
    thread && thread.turns.length > 0 ? thread.turns[thread.turns.length - 1]?.started_at : null;
  const elapsedAnchor = isRunning ? activeTurnStartedAt : thread?.last_activity;
  const liveElapsed = useElapsed(elapsedAnchor, Boolean(isRunning));
  const phases = liveSteps.flatMap((step) => (step.type === "phase" ? [step.phase] : []));
  const reconnectErrorSuppressed = thread?.state === "error" && error?.startsWith("Stream disconnected.");
  const rawStatus = useMemo(() => {
    if (interruptError) return interruptError;
    if (error && !reconnectErrorSuppressed) return error;
    if (isReconnecting && thread?.state !== "error") return "Reconnecting stream...";
    if (agentStatus) return agentStatus;
    if (hasStreamingConnection) return "Live UI stream connected";
    return null;
  }, [agentStatus, error, hasStreamingConnection, interruptError, isReconnecting, reconnectErrorSuppressed, thread?.state]);
  const stableStatus = useStableStatus(rawStatus, 400);
  const slackUrl = thread ? slackUrlForThread(thread.slack_thread_key) : null;

  const stopThreadRun = useCallback(async () => {
    if (!thread || !canInterrupt || isInterrupting) {
      throw new Error("No active run to stop.");
    }
    setInterruptError(null);
    setIsInterrupting(true);
    try {
      await interruptThread();
      fetchThread();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Interrupt failed.";
      setInterruptError(message);
      throw new Error(message);
    } finally {
      setIsInterrupting(false);
    }
  }, [canInterrupt, fetchThread, interruptThread, isInterrupting, thread]);

  const sendFromComposer = useCallback(
    async (message: string) => {
      if (!thread) return false;
      const route = isEngineer && isWaiting ? "reply" : "execute";

      if (isAgentRunning) {
        const shouldInterrupt = window.confirm(
          "This will interrupt the current run and send your new message. Continue?",
        );
        if (!shouldInterrupt) return false;
        await stopThreadRun();
      }

      await sendThreadMessage(message, {
        route,
        ...(route === "execute" && thread.harness !== "engineer" ? { harness: thread.harness } : {}),
      });
      fetchThread();
      return true;
    },
    [fetchThread, isAgentRunning, isEngineer, isWaiting, sendThreadMessage, stopThreadRun, thread],
  );

  useEffect(() => {
    const saved = window.localStorage.getItem(COMPACT_MODE_STORAGE_KEY);
    if (saved === "1") setCompactMode(true);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(COMPACT_MODE_STORAGE_KEY, compactMode ? "1" : "0");
  }, [compactMode]);

  const fetchPaletteThreads = useCallback(
    async (force = false) => {
      const now = Date.now();
      if (!force && paletteThreads.length > 0 && now - paletteLoadedAt < PALETTE_REFRESH_INTERVAL_MS) {
        return;
      }
      setIsPaletteLoading(true);
      try {
        const res = await fetch(`${BASE}/api/threads`);
        if (!res.ok) return;
        const data = (await res.json()) as { threads?: ThreadSummary[] };
        setPaletteThreads(Array.isArray(data.threads) ? data.threads : []);
        setPaletteLoadedAt(Date.now());
      } finally {
        setIsPaletteLoading(false);
      }
    },
    [paletteLoadedAt, paletteThreads.length],
  );

  const openPalette = useCallback(() => {
    setPaletteOpen(true);
    void fetchPaletteThreads();
  }, [fetchPaletteThreads]);

  const copyThreadUrl = useCallback(() => {
    const url = window.location.href;
    if ("clipboard" in navigator && navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(url);
      return;
    }
    window.prompt("Copy thread URL:", url);
  }, []);

  const openInSlack = useCallback(() => {
    if (!slackUrl) return;
    window.open(slackUrl, "_blank", "noopener,noreferrer");
  }, [slackUrl]);

  useHotkeys(
    "meta+k,ctrl+k",
    (event) => {
      event.preventDefault();
      openPalette();
    },
    { enableOnFormTags: true },
    [openPalette],
  );

  useHotkeys(
    "meta+.,ctrl+.",
    (event) => {
      event.preventDefault();
      setCompactMode((value) => !value);
    },
    { enableOnFormTags: true },
    [],
  );

  useHotkeys(
    "shift+/",
    (event) => {
      event.preventDefault();
      setShowShortcutHelp(true);
    },
    { enableOnFormTags: true },
    [],
  );

  useHotkeys(
    "r",
    (event) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isEditableTarget(event.target) || paletteOpen) return;
      event.preventDefault();
      fetchThread();
    },
    {},
    [fetchThread, paletteOpen],
  );

  useHotkeys(
    "/",
    (event) => {
      if (
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        event.shiftKey ||
        isEditableTarget(event.target) ||
        paletteOpen
      ) {
        return;
      }
      event.preventDefault();
      openPalette();
    },
    {},
    [openPalette, paletteOpen],
  );

  useHotkeys(
    "s",
    (event) => {
      if (
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        isEditableTarget(event.target) ||
        paletteOpen ||
        !canInterrupt ||
        isInterrupting
      ) {
        return;
      }
      event.preventDefault();
      void stopThreadRun().catch(() => undefined);
    },
    {},
    [canInterrupt, isInterrupting, paletteOpen, stopThreadRun],
  );

  useHotkeys(
    "escape",
    (event) => {
      if (showShortcutHelp) {
        event.preventDefault();
        setShowShortcutHelp(false);
        return;
      }
      if (paletteOpen) {
        event.preventDefault();
        setPaletteOpen(false);
        return;
      }
      if (isEditableTarget(event.target)) {
        (event.target as HTMLElement | null)?.blur?.();
        return;
      }
      event.preventDefault();
      router.push("/threads");
    },
    { enableOnFormTags: true },
    [paletteOpen, router, showShortcutHelp],
  );

  useEffect(() => {
    if (!thread) return;
    const previousTitle = document.title;
    if (thread.state === "working" || thread.state === "running") {
      document.title = `Working - ${humanName}`;
    } else if (thread.state === "waiting") {
      document.title = `Input needed - ${humanName}`;
    } else if (thread.state === "error") {
      document.title = `Error - ${humanName}`;
    } else {
      document.title = `Done - ${humanName}`;
    }
    return () => {
      document.title = previousTitle;
    };
  }, [humanName, thread]);

  if (error && !thread) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center bg-background">
        <div className="text-center">
          <p className="mb-4 text-sm text-destructive">{error}</p>
          <button
            type="button"
            onClick={fetchThread}
            className="rounded-sm border border-border bg-transparent px-3 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!thread) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center bg-background">
        <div className="text-center">
          <p className="inline-flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin text-primary" />
            Connecting...
          </p>
          <p className="mt-2 font-mono text-xs text-muted-foreground">{threadName(threadKey)}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <div className="shrink-0 border-b border-border bg-background">
        <div className="mx-auto w-full max-w-[980px] px-4 py-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              onClick={openPalette}
              aria-label="Open command menu"
              className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground md:hidden"
            >
              <Menu className="size-4" />
            </button>
            <HarnessBadge harness={thread.harness} />
            <span className="min-w-0 truncate text-[12px] font-medium text-foreground">{humanName}</span>
            <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-muted-foreground">
              <StateDot state={thread.state} />
              {thread.state}
            </span>
          </div>

          <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted-foreground">
            <ParticipantAvatars participants={thread.participants} size={20} />
            <span>
              {thread.turns.length} turn{thread.turns.length === 1 ? "" : "s"}
            </span>
            <span className="inline-flex items-center gap-1">
              <Timer className="size-3.5" />
              {liveElapsed}
            </span>
            <button
              type="button"
              onClick={() => setCompactMode((value) => !value)}
              aria-pressed={compactMode}
              className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-1 text-[11px] transition-colors hover:bg-accent hover:text-foreground"
            >
              <CompactDensityIcon className="size-3.5" />
              {compactMode ? "Compact on" : "Compact off"}
            </button>
            <button
              type="button"
              onClick={openPalette}
              className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-1 text-[11px] transition-colors hover:bg-accent hover:text-foreground"
            >
              <CommandSurfaceIcon className="size-3.5" />
              Palette
            </button>
            <Popover>
              <PopoverTrigger asChild>
                <button
                  type="button"
                  className="cursor-pointer text-muted-foreground transition-colors hover:text-foreground"
                  aria-label="Show thread metadata"
                >
                  <Info className="size-3.5" />
                </button>
              </PopoverTrigger>
              <PopoverContent className="w-[320px]">
                <div className="space-y-2 text-xs">
                  <div className="font-semibold text-foreground">Debug IDs</div>
                  <div className="break-all font-mono text-muted-foreground">{thread.slack_thread_key}</div>
                  {thread.agent_thread_id ? (
                    <div className="break-all font-mono text-muted-foreground">{thread.agent_thread_id}</div>
                  ) : null}
                </div>
              </PopoverContent>
            </Popover>
            {canInterrupt ? (
              <button
                type="button"
                onClick={() => void stopThreadRun().catch(() => undefined)}
                disabled={isInterrupting}
                className="inline-flex items-center gap-1 rounded-sm bg-transparent p-0 text-[11px] text-destructive transition-colors hover:opacity-80 disabled:opacity-60"
              >
                <CircleStop className={isInterrupting ? "size-3.5 animate-pulse" : "size-3.5"} />
                {isInterrupting ? "Stopping..." : "Stop"}
              </button>
            ) : null}
            <button
              type="button"
              onClick={fetchThread}
              className="inline-flex items-center gap-1 rounded-sm bg-transparent p-0 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              <RefreshCw className="size-3.5" />
              Refresh
            </button>
          </div>

          {isEngineer && phases.length > 0 ? (
            <div className="mt-2">
              <PhaseProgress phases={phases} />
            </div>
          ) : null}
        </div>
      </div>

      <div className="mx-auto flex min-h-0 w-full max-w-[980px] flex-1 flex-col">
        <ActivityFeed
          steps={liveSteps}
          state={thread.state}
          compactMode={compactMode}
          participants={thread.participants}
        />
        <StatusBar
          statusText={stableStatus}
          tokenUsage={tokenUsage}
          isRunning={isAgentRunning}
          isReconnecting={isReconnecting}
        />
        <div className="shrink-0 px-4 pb-3 sm:px-5">
          <MessageInput
            mode={isEngineer && isWaiting ? "reply" : "execute"}
            state={thread.state}
            isAgentRunning={isAgentRunning}
            onSend={sendFromComposer}
            onStop={stopThreadRun}
          />
        </div>
      </div>

      {paletteOpen ? (
        <CommandPalette
          open={paletteOpen}
          onOpenChange={setPaletteOpen}
          threads={paletteThreads}
          currentThreadKey={thread.slack_thread_key}
          compactMode={compactMode}
          canInterrupt={canInterrupt}
          isRefreshing={isReconnecting || isPaletteLoading}
          onNavigate={(targetThreadKey) => {
            router.push(`/threads/${encodeURIComponent(targetThreadKey)}`);
          }}
          onRefresh={fetchThread}
          onStop={() => void stopThreadRun().catch(() => undefined)}
          onCopyUrl={copyThreadUrl}
          onToggleCompact={() => setCompactMode((value) => !value)}
          onOpenSlack={slackUrl ? openInSlack : null}
          onOpenShortcuts={() => setShowShortcutHelp(true)}
        />
      ) : null}
      {showShortcutHelp ? <ShortcutHelpDialog onClose={() => setShowShortcutHelp(false)} /> : null}
    </div>
  );
}
