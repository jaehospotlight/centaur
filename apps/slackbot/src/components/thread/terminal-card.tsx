"use client";

import { ChevronRight, CircleCheck, CircleX } from "lucide-react";

export function TerminalCard({
  description,
  command,
  output,
  exitCode,
}: {
  description: string;
  command: string;
  output?: string;
  exitCode?: number;
}) {
  return (
    <details className="group step-item rounded-sm border border-border bg-card">
      <summary className="list-none cursor-pointer px-3 py-2 flex items-center gap-2 [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3.5 text-muted-foreground transition-transform group-open:rotate-90" />
        <span className="text-sm text-foreground">{description}</span>
        {typeof exitCode === "number" && (
          <span className="ml-auto inline-flex items-center gap-1 text-xs">
            {exitCode === 0 ? (
              <CircleCheck className="size-3.5 text-primary" />
            ) : (
              <CircleX className="size-3.5 text-destructive" />
            )}
            <span className={exitCode === 0 ? "text-primary" : "text-destructive"}>exit {exitCode}</span>
          </span>
        )}
      </summary>
      <div className="border-t border-border px-3 py-2 space-y-2">
        <pre className="rounded-sm bg-background p-2 text-[11px] text-foreground overflow-auto whitespace-pre-wrap">
          $ {command}
        </pre>
        {output && (
          <pre className="rounded-sm bg-background p-2 text-[11px] text-muted-foreground overflow-auto max-h-[320px] whitespace-pre-wrap">
            {output}
          </pre>
        )}
      </div>
    </details>
  );
}
