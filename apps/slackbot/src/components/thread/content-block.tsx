"use client";

import { useId, useState } from "react";
import type { ContentBlock as ContentBlockType } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ToolCallCard } from "./tool-call-card";
import { ThinkingView } from "./thinking-view";
import { MarkdownView } from "./markdown-view";

function ToolResultView({ block }: { block: ContentBlockType & { type: "tool_result" } }) {
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();
  const isString = typeof block.content === "string";
  const stringContent: string = typeof block.content === "string" ? block.content : "";
  const content = isString ? stringContent : JSON.stringify(block.content, null, 2);
  const truncated = content.length > 500;
  const preview = truncated ? content.slice(0, 500) + "…" : content;

  return (
    <div className="mt-0.5 border border-zinc-800/50 rounded-md overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls={panelId}
        aria-label={expanded ? "Collapse tool result" : "Expand tool result"}
        className="flex items-center gap-2 w-full bg-zinc-900/40 px-3 py-1.5 cursor-pointer text-left hover:bg-zinc-800/40 transition-colors duration-150"
      >
        <span
          className={cn(
            "inline-block w-0 h-0 shrink-0 transition-transform duration-150",
            "border-t-[4px] border-t-transparent border-b-[4px] border-b-transparent border-l-[5px] border-l-zinc-600",
            expanded && "rotate-90",
          )}
        />
        <span className="text-zinc-500 font-mono text-[11px]">
          result &rarr; {block.tool_use_id?.slice(0, 12)}
        </span>
        <span className="ml-auto text-zinc-700 font-mono text-[10px]">
          {content.length.toLocaleString()} chars
        </span>
      </button>
      <div
        id={panelId}
        className="grid transition-[grid-template-rows] duration-150 ease-out"
        style={{ gridTemplateRows: expanded ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">
          {isString ? (
            <div className="p-3 bg-zinc-950/80 text-zinc-300 overflow-auto max-h-[400px] border-t border-zinc-800/50">
              <MarkdownView text={stringContent} />
            </div>
          ) : (
            <pre className="p-3 bg-zinc-950/80 font-mono text-[11px] text-zinc-600 overflow-auto max-h-[400px] border-t border-zinc-800/50 whitespace-pre-wrap break-all">
              {content}
            </pre>
          )}
        </div>
      </div>
      {!expanded && truncated && (
        <pre className="px-3 py-2 bg-zinc-950/80 font-mono text-[11px] text-zinc-700 overflow-hidden max-h-[60px] border-t border-zinc-800/50 whitespace-pre-wrap break-all">
          {preview}
        </pre>
      )}
    </div>
  );
}

export function ContentBlockView({ block }: { block: ContentBlockType }) {
  if (block.type === "text" && "text" in block && block.text) {
    return <MarkdownView text={block.text} />;
  }

  if (block.type === "tool_use" && "name" in block) {
    return <ToolCallCard block={block} />;
  }

  if (block.type === "tool_result" && "tool_use_id" in block) {
    return <ToolResultView block={block as ContentBlockType & { type: "tool_result" }} />;
  }

  if (block.type === "thinking" && "thinking" in block) {
    return <ThinkingView text={block.thinking} />;
  }

  return null;
}
