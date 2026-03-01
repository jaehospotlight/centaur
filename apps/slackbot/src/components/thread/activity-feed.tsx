"use client";

import { AlertTriangle, FileDiff, FilePenLine, MessagesSquare, TerminalSquare } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import type { Step } from "@/lib/describe";
import { MarkdownView } from "@/components/thread/markdown-view";
import { DiffCard } from "@/components/thread/diff-card";
import { StepGroup } from "@/components/thread/step-group";
import { TerminalCard } from "@/components/thread/terminal-card";
import { ThinkingDivider } from "@/components/thread/thinking-divider";

function stepKey(step: Step, index: number): string {
  if (step.type === "tool-group") {
    return `tool-group:${step.category}:${step.calls[0]?.id ?? index}`;
  }
  if (step.type === "result") {
    return `result:${step.text.slice(0, 48)}:${index}`;
  }
  if (step.type === "thinking") {
    return `thinking:${step.text.slice(0, 40)}:${index}`;
  }
  if (step.type === "terminal") {
    return `terminal:${step.command.slice(0, 40)}:${index}`;
  }
  if (step.type === "diff") {
    return `diff:${step.file}:${index}`;
  }
  if (step.type === "phase") {
    return `phase:${step.phase}:${index}`;
  }
  if (step.type === "file-changes") {
    return `file-changes:${step.changes[0]?.path ?? "none"}:${index}`;
  }
  if (step.type === "error") {
    return `error:${step.message.slice(0, 40)}:${index}`;
  }
  return `step:${index}`;
}

function renderStep(step: Step, key: string): React.ReactNode {
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
    return <StepGroup key={key} icon={step.icon} summary={step.summary} calls={step.calls} />;
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
  if (step.type === "result") {
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

export function ActivityFeed({ steps, state }: { steps: Step[]; state?: string }) {
  const activeCount = steps.length;
  const { containerRef, sentinelRef } = useAutoScroll([steps]);
  const [pendingSteps, setPendingSteps] = useState(0);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const previousCountRef = useRef(activeCount);

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
        aria-live="polite"
        onScroll={handleScroll}
        className="h-full overflow-y-auto px-5 py-4 space-y-4"
      >
      {activeCount === 0 ? (
        <div className="h-full flex items-center justify-center text-sm text-muted-foreground gap-2">
          <TerminalSquare className="size-4 text-primary" />
          {state === "idle" ? "No events yet. This thread is idle." : "Waiting for events…"}
        </div>
      ) : (
        steps.map((step, index) => renderStep(step, stepKey(step, index)))
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
