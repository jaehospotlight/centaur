"use client";

import { ChevronRight, CircleCheck, CircleX, LoaderCircle } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { describeToolCall, type ToolCall } from "@/lib/describe";
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
  icon: Icon,
  summary,
  calls,
}: {
  icon: React.ComponentType<{ className?: string }>;
  summary: string;
  calls: ToolCall[];
}) {
  const loadingCount = calls.filter((call) => call.state === "loading" || !call.state).length;
  const errorCount = calls.filter((call) => call.state === "error").length;
  const doneCount = calls.filter((call) => call.state === "done").length;

  return (
    <Collapsible className="group step-item rounded-sm border border-border bg-card">
      <CollapsibleTrigger className="w-full flex items-center gap-2 px-3 py-2 hover:bg-accent cursor-pointer">
        <ChevronRight className="size-3.5 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
        <Icon className="size-3.5 text-primary" />
        <span className="text-sm text-foreground">{summary}</span>
        {errorCount > 0 ? (
          <CircleX className="ml-auto size-3.5 text-destructive" />
        ) : loadingCount > 0 ? (
          <LoaderCircle className="ml-auto size-3.5 text-muted-foreground animate-spin" />
        ) : (
          <CircleCheck className="ml-auto size-3.5 text-primary" />
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
      </CollapsibleTrigger>
      <CollapsibleContent className="px-3 pb-2 pl-8 space-y-1">
        {calls.map((call) => (
          <ToolCallItem key={call.id} call={call} />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}
