"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, CircleCheck, CircleX, LoaderCircle } from "lucide-react";
import { ToolArgumentsIcon } from "@/components/thread/icons/thread-icons";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { describeToolCall, singleCallOutputBadge, type ToolCall } from "@/lib/describe";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

function ToolStateIcon({ state }: { state?: ToolCall["state"] }) {
  if (state === "done") return <CircleCheck className="size-3.5 text-primary" />;
  if (state === "error") return <CircleX className="size-3.5 text-destructive" />;
  return <LoaderCircle className="size-3.5 text-muted-foreground animate-spin" />;
}

function ToolCallItem({ call }: { call: ToolCall }) {
  return (
    <Collapsible className="group">
      <CollapsibleTrigger className="w-full flex items-center gap-2 py-1 text-xs text-muted-foreground hover:text-foreground cursor-pointer">
        <ChevronRight className="size-3 transition-transform group-data-[state=open]:rotate-90" />
        <ToolStateIcon state={call.state} />
        <span className="truncate">{describeToolCall(call.name, call.input)}</span>
        {call.output && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="ml-auto tabular-nums text-[11px]">
                {call.output.length.toLocaleString()} chars
              </span>
            </TooltipTrigger>
            <TooltipContent>
              State: {call.state ?? "loading"} · Output: {call.output.length.toLocaleString()} chars
            </TooltipContent>
          </Tooltip>
        )}
      </CollapsibleTrigger>
      <CollapsibleContent>
        {call.output ? (
          <pre className="ml-5 rounded-sm bg-background p-2 text-[11px] text-muted-foreground overflow-auto max-h-[260px] whitespace-pre-wrap">
            {call.output}
          </pre>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

export function StepGroup({
  id,
  icon: Icon,
  summary,
  calls,
  compactMode = false,
}: {
  id: string;
  icon: React.ComponentType<{ className?: string }>;
  summary: string;
  calls: ToolCall[];
  compactMode?: boolean;
}) {
  const { loadingCount, errorCount, doneCount, outputBadge } = useMemo(() => {
    let loading = 0;
    let error = 0;
    let done = 0;
    for (const call of calls) {
      if (call.state === "error") {
        error += 1;
      } else if (call.state === "done") {
        done += 1;
      } else {
        loading += 1;
      }
    }
    return {
      loadingCount: loading,
      errorCount: error,
      doneCount: done,
      outputBadge: singleCallOutputBadge(calls),
    };
  }, [calls]);
  const allComplete = calls.length > 0 && loadingCount === 0;
  const [open, setOpen] = useState(() => !allComplete || !compactMode);
  const [manuallyToggled, setManuallyToggled] = useState(false);
  const wasCompleteRef = useRef(allComplete);

  useEffect(() => {
    const wasComplete = wasCompleteRef.current;
    wasCompleteRef.current = allComplete;
    if (manuallyToggled) return;

    if (!allComplete) {
      setOpen(true);
      return;
    }

    if (!wasComplete) {
      const timeout = window.setTimeout(() => setOpen(false), 300);
      return () => window.clearTimeout(timeout);
    }

    if (compactMode) {
      setOpen(false);
    }
  }, [allComplete, compactMode, manuallyToggled]);

  function handleOpenChange(nextOpen: boolean) {
    setManuallyToggled(true);
    setOpen(nextOpen);
  }

  return (
    <Collapsible
      open={open}
      onOpenChange={handleOpenChange}
      data-group-id={id}
      className="group step-item rounded-sm border border-border bg-card"
    >
      <CollapsibleTrigger className="w-full flex items-center gap-2 px-3 py-2 hover:bg-accent cursor-pointer">
        <ChevronRight className="size-3.5 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
        <Icon className="size-3.5 text-primary" />
        <span className="text-sm text-foreground truncate">{summary}</span>
        <div className="ml-auto flex items-center gap-2">
          {outputBadge ? (
            <span className="inline-flex items-center gap-1 tabular-nums text-[11px] text-muted-foreground">
              <ToolArgumentsIcon className="size-3" />
              {outputBadge}
            </span>
          ) : null}
          {errorCount > 0 ? (
            <CircleX className="size-3.5 text-destructive" />
          ) : loadingCount > 0 ? (
            <LoaderCircle className="size-3.5 text-muted-foreground animate-spin" />
          ) : (
            <CircleCheck className="size-3.5 text-primary" />
          )}
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="text-xs text-muted-foreground">
                {doneCount}/{calls.length}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              Done: {doneCount} · Loading: {loadingCount} · Errors: {errorCount}
            </TooltipContent>
          </Tooltip>
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent className="px-3 pb-2 pl-8 space-y-1">
        {calls.map((call) => (
          <ToolCallItem key={call.id} call={call} />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}
