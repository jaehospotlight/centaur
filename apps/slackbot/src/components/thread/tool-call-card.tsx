"use client";

import { useId, useState } from "react";
import type { ToolUseBlock } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SmartToolView } from "./smart-tool-view";

function extractToolSummary(block: ToolUseBlock): string {
  const input = block.input as Record<string, unknown>;
  switch (block.name) {
    case "read_file":
    case "write_file":
    case "str_replace":
      return String(input.path ?? "");
    case "shell":
      return String(input.command ?? "").slice(0, 60);
    case "grep_search": {
      const parts = [String(input.pattern ?? "")];
      if (input.glob) parts.push(`glob=${input.glob}`);
      return parts.join("  ");
    }
    default:
      return "";
  }
}

export function ToolCallCard({
  block,
  hasError,
}: {
  block: ToolUseBlock;
  hasError?: boolean;
}) {
  const [expanded, setExpanded] = useState(hasError ?? false);
  const panelId = useId();
  const summary = extractToolSummary(block);

  return (
    <div
      className={cn(
        "mt-1 border rounded-md overflow-hidden",
        hasError
          ? "border-red-500/30 border-l-2 border-l-red-500"
          : "border-zinc-800/50",
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls={panelId}
        aria-label={expanded ? `Collapse ${block.name} tool call` : `Expand ${block.name} tool call`}
        className="flex items-center gap-2 w-full bg-zinc-900/60 px-3 py-1.5 cursor-pointer text-left hover:bg-zinc-800/40 transition-colors duration-150"
      >
        <span
          className={cn(
            "inline-block w-0 h-0 shrink-0 transition-transform duration-150",
            "border-t-[4px] border-t-transparent border-b-[4px] border-b-transparent border-l-[5px] border-l-zinc-600",
            expanded && "rotate-90",
          )}
        />
        <span className="text-amber-500 font-mono font-semibold text-[13px]">
          {block.name}
        </span>
        {summary && (
          <span className="text-zinc-400 font-mono text-[13px] truncate">
            {summary}
          </span>
        )}
        <span className="ml-auto text-zinc-700 font-mono text-[11px] shrink-0">
          {block.id?.slice(0, 12)}
        </span>
      </button>
      <div
        id={panelId}
        className="grid transition-[grid-template-rows] duration-150 ease-out"
        style={{ gridTemplateRows: expanded ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">
          <SmartToolView block={block} />
        </div>
      </div>
    </div>
  );
}
