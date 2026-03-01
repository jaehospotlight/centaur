"use client";

import type { TokenUsage } from "@/hooks/use-thread-stream";
import { AgentRunIcon } from "@/components/thread/icons/thread-icons";
import { cn } from "@/lib/utils";

type StatusBarProps = {
  statusText: string | null;
  tokenUsage: TokenUsage | null;
  isRunning: boolean;
  isReconnecting?: boolean;
};

function formatK(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0";
  if (value < 1000) return String(Math.round(value));
  if (value < 10000) return `${(value / 1000).toFixed(1)}k`;
  return `${Math.round(value / 1000)}k`;
}

function estimateContextWindow(model: string | null): number {
  const lower = String(model ?? "").toLowerCase();
  if (!lower) return 200_000;
  if (lower.includes("haiku")) return 200_000;
  if (lower.includes("sonnet")) return 200_000;
  if (lower.includes("opus")) return 200_000;
  if (lower.includes("gpt-4.1") || lower.includes("o1") || lower.includes("o3")) return 1_000_000;
  if (lower.includes("gpt-4") || lower.includes("gpt-5")) return 128_000;
  return 200_000;
}

function contextPercent(usage: TokenUsage | null): number | null {
  if (!usage || usage.total_tokens <= 0) return null;
  const maxContext = estimateContextWindow(usage.model);
  return Math.max(0, Math.min(100, Math.round((usage.total_tokens / maxContext) * 100)));
}

function contextTone(percent: number | null): string {
  if (percent === null) return "text-muted-foreground";
  if (percent < 50) return "text-primary";
  if (percent <= 80) return "text-amber-400";
  return "text-destructive";
}

function formatCost(usage: TokenUsage | null): string {
  if (!usage || usage.cost_usd === null) return "$--";
  const rounded = usage.cost_usd >= 0.1 ? usage.cost_usd.toFixed(2) : usage.cost_usd.toFixed(4);
  return `${usage.estimated ? "~" : ""}$${rounded}`;
}

export function StatusBar({ statusText, tokenUsage, isRunning, isReconnecting = false }: StatusBarProps) {
  const contextPct = contextPercent(tokenUsage);
  const activeStatus = statusText ?? (isReconnecting ? "Reconnecting stream..." : isRunning ? "Working..." : null);
  const model = tokenUsage?.model ?? "--";
  const inputK = tokenUsage ? formatK(tokenUsage.input_tokens) : "--";
  const outputK = tokenUsage ? formatK(tokenUsage.output_tokens) : "--";
  const totalK = tokenUsage ? formatK(tokenUsage.total_tokens) : "--";
  const cost = formatCost(tokenUsage);

  return (
    <div className="shrink-0 border-t border-border bg-background/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-[960px] items-center px-5 py-2">
        <div className="hidden min-w-0 flex-1 items-center gap-2 text-[11px] text-muted-foreground sm:flex">
          {activeStatus ? (
            <>
              <AgentRunIcon
                className={cn(
                  "size-3.5",
                  isRunning || isReconnecting
                    ? "animate-pulse text-primary"
                    : "text-muted-foreground",
                )}
                aria-hidden="true"
              />
              <span className="truncate text-foreground">{activeStatus}</span>
            </>
          ) : (
            <span className="text-muted-foreground"> </span>
          )}
          <span className="ml-auto">{model}</span>
          <span className={cn("tabular-nums", contextTone(contextPct))}>
            ctx {contextPct === null ? "--" : `${contextPct}%`}
          </span>
          <span className="tabular-nums">
            {inputK}/{outputK}
          </span>
          <span className="tabular-nums">{cost}</span>
        </div>
        <div className="flex w-full items-center justify-between gap-2 text-[11px] sm:hidden">
          {activeStatus ? (
            <span className="min-w-0 truncate text-muted-foreground">{activeStatus}</span>
          ) : (
            <span />
          )}
          <span className="tabular-nums text-muted-foreground">
            <span className={cn(contextTone(contextPct))}>
              ctx {contextPct === null ? "--" : `${contextPct}%`}
            </span>{" "}
            {totalK} tok {cost}
          </span>
        </div>
      </div>
    </div>
  );
}
