"use client";

import { useMemo } from "react";
import { ChevronRight, CircleCheck, CircleX, LoaderCircle } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  describeToolCall,
  describeToolCallMetaChips,
  singleCallOutputBadge,
  type ToolCall,
  type ToolCallMetaChip,
} from "@/lib/describe";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

function ToolStateIcon({ state }: { state?: ToolCall["state"] }) {
  if (state === "done") return <CircleCheck className="size-3.5 text-primary" />;
  if (state === "error") return <CircleX className="size-3.5 text-destructive" />;
  return <LoaderCircle className="size-3.5 text-muted-foreground animate-spin" />;
}

const CHIP_LABEL: Record<ToolCallMetaChip["key"], string> = {
  path: "path",
  query: "query",
  cwd: "cwd",
  glob: "glob",
  recursive: "recursive",
  lines: "lines",
};

function ToolMetaChips({ chips }: { chips: ToolCallMetaChip[] }) {
  const visible = chips.slice(0, 4);
  const hidden = chips.length - visible.length;

  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      {visible.map((chip) => (
        <span
          key={`${chip.key}:${chip.value}`}
          title={chip.fullValue ?? chip.value}
          className="inline-flex h-5 max-w-full items-center gap-1 rounded-[6px] border border-border/70 bg-muted/40 px-1.5 text-[10px] leading-none text-muted-foreground"
        >
          <span className="font-mono uppercase tracking-wide text-[9px] text-muted-foreground/80">
            {CHIP_LABEL[chip.key]}
          </span>
          <span className="max-w-[24ch] truncate text-foreground/85">{chip.value}</span>
        </span>
      ))}
      {hidden > 0 ? (
        <span className="inline-flex h-5 items-center rounded-[6px] border border-border/60 bg-muted/30 px-1.5 text-[10px] text-muted-foreground">
          +{hidden}
        </span>
      ) : null}
    </div>
  );
}

function ToolCallItem({ call }: { call: ToolCall }) {
  const summary = useMemo(() => describeToolCall(call.name, call.input), [call.name, call.input]);
  const chips = useMemo(
    () => describeToolCallMetaChips(call.name, call.input),
    [call.name, call.input],
  );

  return (
    <Collapsible className="group">
      <CollapsibleTrigger className="w-full min-h-10 flex items-start gap-2 py-1.5 text-xs text-muted-foreground hover:text-foreground cursor-pointer">
        <ChevronRight className="mt-0.5 size-3 shrink-0 transition-transform group-data-[state=open]:rotate-90" />
        <ToolStateIcon state={call.state} />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-foreground/90" title={summary}>
              {summary}
            </span>
            {call.output && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="ml-auto shrink-0 tabular-nums text-[11px]">
                    {call.output.length.toLocaleString()} chars
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  State: {call.state ?? "loading"} · Output: {call.output.length.toLocaleString()} chars
                </TooltipContent>
              </Tooltip>
            )}
          </div>
          {chips.length > 0 ? <ToolMetaChips chips={chips} /> : null}
        </div>
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
  icon: Icon,
  summary,
  calls,
}: {
  icon: React.ComponentType<{ className?: string }>;
  summary: string;
  calls: ToolCall[];
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

  return (
    <Collapsible defaultOpen={errorCount > 0} className="group step-item rounded-sm border border-border bg-card">
      <CollapsibleTrigger className="w-full min-h-11 flex items-center gap-2 px-3 py-2 hover:bg-accent cursor-pointer">
        <ChevronRight className="size-3.5 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
        <Icon className="size-3.5 text-primary" />
        <span className="text-sm text-foreground truncate" title={summary}>
          {summary}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {outputBadge ? (
            <span className="tabular-nums text-[11px] text-muted-foreground">{outputBadge}</span>
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
              <span className="text-xs text-muted-foreground" aria-label={`Done ${doneCount}, loading ${loadingCount}, errors ${errorCount}`}>
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
