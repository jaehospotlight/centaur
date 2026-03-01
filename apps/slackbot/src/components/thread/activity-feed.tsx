"use client";

import { AlertTriangle, ChevronRight, FileDiff, FilePenLine, MessagesSquare, TerminalSquare } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ThreadContextIcon } from "@/components/thread/icons/thread-icons";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import type { Step } from "@/lib/describe";
import type { Participant } from "@/lib/types";
import { MarkdownView } from "@/components/thread/markdown-view";
import { DiffCard } from "@/components/thread/diff-card";
import { StepGroup } from "@/components/thread/step-group";
import { TerminalCard } from "@/components/thread/terminal-card";
import { ThinkingDivider } from "@/components/thread/thinking-divider";

function sourceLabel(source?: string): string {
  const normalized = (source || "").toLowerCase();
  if (normalized === "thread_ui" || normalized === "thread-view" || normalized === "ui") {
    return "Thread Viewer";
  }
  if (normalized === "slack" || normalized === "slack_subscribed_message") {
    return "Slack";
  }
  return normalized || "User";
}

function initials(label: string): string {
  const parts = label.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

function renderStep(
  step: Step,
  options: {
    compactMode: boolean;
    keepExpandedResultIds: Set<string>;
    participantsById: Map<string, Participant>;
  },
): React.ReactNode {
  const { compactMode, keepExpandedResultIds, participantsById } = options;
  const key = step.id;
  if (step.type === "phase") {
    return (
      <div key={key} className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-muted-foreground">
        <FileDiff className="size-3 text-primary" />
        {step.phase}
      </div>
    );
  }
  if (step.type === "thinking") return <ThinkingDivider key={key} text={step.text} durationS={step.durationS} />;
  if (step.type === "tool-group") {
    return (
      <StepGroup
        key={key}
        id={step.id}
        icon={step.icon}
        summary={step.summary}
        calls={step.calls}
        compactMode={compactMode}
      />
    );
  }
  if (step.type === "diff") {
    return <DiffCard key={key} file={step.file} lang={step.lang} oldStr={step.oldStr} newStr={step.newStr} />;
  }
  if (step.type === "terminal") {
    return (
      <TerminalCard
        key={key}
        description={step.description}
        command={step.command}
        output={step.output}
        exitCode={step.exitCode}
      />
    );
  }
  if (step.type === "file-changes") {
    return (
      <div key={key} className="step-item rounded-sm border border-border bg-card px-3 py-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1.5">
          <FilePenLine className="size-3.5 text-primary" />
          File changes
        </div>
        <div className="space-y-1">
          {step.changes.map((change, index) => (
            <div key={`${change.path}-${index}`} className="text-xs font-mono text-muted-foreground">
              {change.kind} {change.path}
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (step.type === "error") {
    return (
      <div key={key} className="step-item rounded-sm border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive flex items-center gap-2">
        <AlertTriangle className="size-4 shrink-0" />
        {step.message}
      </div>
    );
  }
  if (step.type === "user-message") {
    const participant = step.userId ? participantsById.get(step.userId) : undefined;
    const displayName = participant?.name || step.userId || "User";
    return (
      <div key={key} className="step-item rounded-sm border border-border/50 bg-card px-3 py-2">
        <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
          <div className="flex min-w-0 items-center gap-2 text-muted-foreground">
            <div className="size-5 rounded-full bg-secondary text-secondary-foreground inline-flex items-center justify-center text-[10px] font-semibold overflow-hidden">
              {participant?.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={participant.avatar_url}
                  alt={displayName}
                  className="h-full w-full object-cover"
                />
              ) : (
                initials(displayName)
              )}
            </div>
            <span className="truncate text-foreground">{displayName}</span>
          </div>
          <span className="shrink-0 rounded border border-border bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
            {sourceLabel(step.source)}
          </span>
        </div>
        <div className="text-sm whitespace-pre-wrap break-words">{step.text}</div>
      </div>
    );
  }
  if (step.type === "context-group") {
    return (
      <details
        key={key}
        className="step-item rounded-sm border border-dashed border-border bg-card/60 px-3 py-2"
      >
        <summary className="cursor-pointer list-none text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <ThreadContextIcon className="size-3.5" />
            {step.title} ({step.items.length} message{step.items.length === 1 ? "" : "s"})
          </span>
        </summary>
        <div className="mt-2 space-y-1.5">
          {step.items.map((item) => {
            const participant = item.userId ? participantsById.get(item.userId) : undefined;
            const displayName = participant?.name || item.userId || "thread-user";
            return (
              <div key={item.id} className="text-xs text-muted-foreground break-words">
                <span className="font-medium text-foreground/90">@{displayName}:</span> {item.text}
              </div>
            );
          })}
        </div>
      </details>
    );
  }
  if (step.type === "result") {
    if (compactMode && !keepExpandedResultIds.has(step.id)) {
      const previewLine = step.text.split("\n").map((line) => line.trim()).find(Boolean) ?? "Result";
      return (
        <details key={key} className="group step-item rounded-sm border border-border bg-card">
          <summary className="list-none cursor-pointer px-3 py-2 flex items-center gap-2 [&::-webkit-details-marker]:hidden">
            <ChevronRight className="size-3.5 text-muted-foreground transition-transform group-open:rotate-90" />
            <MessagesSquare className="size-3.5 text-primary" />
            <span className="text-xs text-muted-foreground">Result</span>
            <span className="truncate text-sm text-foreground">{previewLine}</span>
          </summary>
          <div className="border-t border-border px-3 py-2">
            <MarkdownView text={step.text} isStreaming={step.streaming} />
          </div>
        </details>
      );
    }
    return (
      <div key={key} className="step-item rounded-sm border border-border bg-card px-3 py-2">
        <div className="flex items-center gap-2 mb-1 text-xs text-muted-foreground">
          <MessagesSquare className="size-3.5 text-primary" />
          Result
        </div>
        <div className="relative">
          <MarkdownView text={step.text} isStreaming={step.streaming} />
        </div>
      </div>
    );
  }
  return null;
}

export function ActivityFeed({
  steps,
  state,
  compactMode = false,
  participants,
}: {
  steps: Step[];
  state?: string;
  compactMode?: boolean;
  participants?: Participant[];
}) {
  const activeCount = steps.length;
  const isStreamingState = state === "running" || state === "working";
  const { containerRef, sentinelRef } = useAutoScroll([steps]);
  const [pendingSteps, setPendingSteps] = useState(0);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const previousCountRef = useRef(activeCount);
  const keepExpandedResultIds = useMemo(() => {
    const resultIds = steps.filter((step) => step.type === "result").map((step) => step.id);
    return new Set(resultIds.slice(-2));
  }, [steps]);
  const participantsById = useMemo(() => {
    const map = new Map<string, Participant>();
    for (const participant of participants || []) {
      map.set(participant.id, participant);
    }
    return map;
  }, [participants]);

  useEffect(() => {
    if (activeCount <= previousCountRef.current) {
      previousCountRef.current = activeCount;
      return;
    }
    const delta = activeCount - previousCountRef.current;
    previousCountRef.current = activeCount;
    if (!isNearBottom) {
      setPendingSteps((value) => value + delta);
    }
  }, [activeCount, isNearBottom]);

  function handleScroll() {
    const container = containerRef.current;
    if (!container) return;
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 120;
    setIsNearBottom(nearBottom);
    if (nearBottom) setPendingSteps(0);
  }

  function jumpToLatest() {
    sentinelRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    setPendingSteps(0);
  }

  return (
    <div className="relative flex-1 min-h-0">
      <div
        ref={containerRef}
        role="log"
        aria-live={isStreamingState ? "off" : "polite"}
        aria-busy={isStreamingState}
        onScroll={handleScroll}
        className="h-full overflow-y-auto overscroll-contain scroll-pb-28 px-5 py-4 space-y-4"
      >
      {activeCount === 0 ? (
        <div className="h-full flex items-center justify-center text-sm text-muted-foreground gap-2">
          <TerminalSquare className="size-4 text-primary" />
          {state === "idle" ? "No events yet. This thread is idle." : "Waiting for events…"}
        </div>
      ) : (
        steps.map((step) =>
          renderStep(step, { compactMode, keepExpandedResultIds, participantsById })
        )
      )}
      <div ref={sentinelRef} className="h-px" />
      </div>
      {pendingSteps > 0 && (
        <button
          type="button"
          onClick={jumpToLatest}
          aria-label={`Jump to latest, ${pendingSteps} new step${pendingSteps === 1 ? "" : "s"}`}
          className="absolute bottom-4 right-5 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-foreground shadow-md hover:bg-accent cursor-pointer"
        >
          ↓ {pendingSteps} new step{pendingSteps === 1 ? "" : "s"}
        </button>
      )}
    </div>
  );
}
