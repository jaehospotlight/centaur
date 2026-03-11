"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowUp,
  Bot,
  CircleStop,
  Command,
  Info,
  Menu,
  RefreshCw,
  Timer,
} from "lucide-react";
import type { ThreadDetail, ThreadTokenUsage } from "@/lib/types";
import {
  formatTokenUsageCount,
  formatTokenUsageTicker,
  tokenUsageBreakdownLabel,
  tokenUsageConfidenceLabel,
  tokenUsageModelLabel,
  tokenUsageModelsList,
} from "@/lib/token-usage";
import { Button } from "@/components/ui/button";
import { useHaptics } from "@/components/haptics-provider";
import { SurfaceBar } from "@/components/ui/surface-bar";
import { HarnessBadge } from "@/components/ui/harness-badge";
import { StateDot } from "@/components/ui/state-dot";
import { ParticipantAvatars } from "@/components/thread/participant-avatars";
import { PhaseProgress } from "@/components/thread/phase-progress";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  categorizeAgentStatusText,
  threadStateLabel,
} from "@/lib/status-semantics";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { TextReveal } from "@/components/ai-elements/text-reveal";

type ThreadDetailHeaderProps = {
  thread: ThreadDetail;
  humanName: string;
  tokenUsage: ThreadTokenUsage | null;
  liveElapsed: string;
  stableStatus: string | null;
  isRunning: boolean;
  isEngineer: boolean;
  phases: string[];
  error: string | null;
  interruptError: string | null;
  canInterrupt: boolean;
  isInterrupting: boolean;
  onInterrupt: () => void;
  onRefresh: () => void;
  onOpenInfo: () => void;
  onOpenPalette?: () => void;
  onOpenDrawer: () => void;
  sourceLabel: string;
  onBack: () => void;
  upHref: string;
};

export function ThreadDetailHeader({
  thread,
  humanName,
  tokenUsage,
  liveElapsed,
  stableStatus,
  isRunning,
  isEngineer,
  phases,
  error,
  interruptError,
  canInterrupt,
  isInterrupting,
  onInterrupt,
  onRefresh,
  onOpenInfo,
  onOpenPalette,
  onOpenDrawer,
  sourceLabel,
  onBack,
  upHref,
}: ThreadDetailHeaderProps) {
  const { trigger } = useHaptics();
  const usageConfidence = tokenUsageConfidenceLabel(tokenUsage);
  const tokenTicker = formatTokenUsageTicker(tokenUsage);
  const modelLabel = tokenUsageModelLabel(tokenUsage);
  const modelList = tokenUsageModelsList(tokenUsage);
  const breakdownLabel = tokenUsageBreakdownLabel(tokenUsage);
  const showError =
    !!error &&
    !(thread.state === "error" && error.startsWith("Stream disconnected."));
  const statusSummary = useMemo(() => {
    if (thread.state === "error") {
      return { icon: Bot, text: error || "Agent encountered an error" };
    }
    if (thread.state === "stopping") {
      return { icon: Bot, text: "Stopping run…" };
    }
    if (isRunning) return categorizeAgentStatusText(stableStatus);
    return { icon: Bot, text: "Idle" };
  }, [error, isRunning, stableStatus, thread.state]);
  const messageLabel = `message${thread.message_count === 1 ? "" : "s"}`;

  return (
    <SurfaceBar className="relative shrink-0 border-b border-border/70">
      <div className="flex items-start gap-3 px-3 py-3.5 md:px-4 md:py-4">
        <Button
          type="button"
          onClick={() => {
            trigger("light");
            onOpenDrawer();
          }}
          variant="ghost"
          size="icon"
          className="ui-control-icon md:hidden"
          aria-label="Open thread list"
          data-touch-target
        >
          <Menu className="size-5" />
        </Button>

        <Button
          type="button"
          onClick={() => {
            trigger("light");
            onBack();
          }}
          variant="ghost"
          size="icon"
          className="ui-control-icon"
          aria-label="Back to source"
          data-touch-target
        >
          <ArrowLeft className="size-4" />
        </Button>

        <Link
          href={upHref}
          scroll={false}
          aria-label="Up to threads"
          className="hidden size-9 items-center justify-center rounded-lg p-1 text-xs ui-control-icon md:inline-flex"
          data-touch-target
        >
          <ArrowUp className="size-3.5" />
        </Link>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <HarnessBadge harness={thread.harness} className="flex-shrink-0" />
            <span className="ui-pill">
              <StateDot state={thread.state} className="flex-shrink-0" />
              <span>{threadStateLabel(thread.state)}</span>
            </span>
            <span className="hidden lg:inline-flex">
              <ParticipantAvatars participants={thread.participants} size={20} />
            </span>
            {tokenTicker ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="ui-pill hidden font-mono tabular-nums lg:inline-flex">
                    {tokenTicker}
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  <div className="space-y-0.5 text-xs">
                    <div>Total: {formatTokenUsageCount(tokenUsage?.total_tokens ?? null)}</div>
                    <div>Input: {formatTokenUsageCount(tokenUsage?.input_tokens ?? null)}</div>
                    <div>Output: {formatTokenUsageCount(tokenUsage?.output_tokens ?? null)}</div>
                    <div>Split: {breakdownLabel}</div>
                    <div>Model: {modelList}</div>
                    <div>Usage: {usageConfidence}</div>
                  </div>
                </TooltipContent>
              </Tooltip>
            ) : null}
          </div>

          <div className="mt-2 flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="truncate text-base font-semibold tracking-tight text-foreground md:text-lg">
                {humanName}
              </div>
              <div className="ui-meta mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <span className="inline-flex items-center gap-1">
                  <statusSummary.icon className="size-3.5 shrink-0" />
                  <TextReveal text={statusSummary.text} />
                </span>
                <span className="ui-caption">{sourceLabel}</span>
                <span className="inline-flex items-center gap-1">
                  <AnimatedNumber value={thread.message_count} /> {messageLabel}
                </span>
                <span className="inline-flex items-center gap-1 tabular-nums">
                  <Timer className="size-3.5" />
                  {liveElapsed}
                </span>
                {!tokenTicker && modelLabel ? (
                  <span className="ui-caption font-mono">{modelLabel}</span>
                ) : null}
              </div>
            </div>

            <div className="flex items-center gap-2">
              {onOpenPalette ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      onClick={() => {
                        trigger("light");
                        onOpenPalette();
                      }}
                      variant="ghost"
                      size="icon"
                      className="hidden ui-control-icon md:inline-flex"
                      aria-label="Command palette"
                      data-touch-target
                    >
                      <Command className="size-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Commands Cmd+K</TooltipContent>
                </Tooltip>
              ) : null}
              <Button
                type="button"
                onClick={() => {
                  trigger("light");
                  onOpenInfo();
                }}
                variant="ghost"
                size="icon"
                className="ui-control-icon"
                aria-label="Thread info"
                data-touch-target
              >
                <Info className="size-4" />
              </Button>

              {canInterrupt && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      onClick={() => {
                        trigger("warning");
                        onInterrupt();
                      }}
                      disabled={isInterrupting}
                      variant="destructive"
                      size="icon"
                      className="size-10 items-center gap-1 border border-destructive/35 bg-destructive/8 text-destructive hover:bg-destructive/14 disabled:opacity-60 md:h-8 md:w-auto md:px-2.5"
                      aria-label={isInterrupting ? "Stop run in progress" : "Stop run"}
                      data-touch-target
                    >
                      <CircleStop
                        className={isInterrupting ? "size-3.5 animate-pulse" : "size-3.5"}
                      />
                      <span className="hidden md:inline">
                        {isInterrupting ? "Stopping…" : "Stop"}
                      </span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Stop Alt+S</TooltipContent>
                </Tooltip>
              )}

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    onClick={() => {
                      trigger("light");
                      onRefresh();
                    }}
                    variant="outline"
                    size="icon"
                    className="size-10 items-center gap-1 border-border/70 bg-card/45 text-muted-foreground hover:bg-accent hover:text-foreground md:h-8 md:w-auto md:px-2.5"
                    aria-label="Refresh thread"
                    data-touch-target
                  >
                    <RefreshCw className="size-3.5" />
                    <span className="hidden md:inline">Refresh</span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Refresh Alt+R</TooltipContent>
              </Tooltip>
            </div>
          </div>
        </div>
      </div>

      {isEngineer && phases.length > 0 && (
        <div className="border-t border-border/50 px-3 py-2 md:px-4">
          <PhaseProgress phases={phases} />
        </div>
      )}

      <div className="sr-only" aria-live="polite" aria-atomic="true">
        Status: {statusSummary.text}
      </div>

      {(showError || !!interruptError) && (
        <div
          role="alert"
          className="inline-flex items-center gap-1.5 border-t border-destructive/30 bg-destructive/10 px-3 py-1.5 text-xs text-destructive md:px-4"
        >
          <AlertTriangle className="size-3.5" />
          {interruptError ??
            (thread.state === "error" && error?.startsWith("Stream disconnected.")
              ? null
              : error)}
        </div>
      )}
    </SurfaceBar>
  );
}
