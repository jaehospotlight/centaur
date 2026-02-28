"use client";

import type { ThreadEvent } from "@/lib/types";
import { ContentBlockView } from "./content-block";
import { ThinkingView } from "./thinking-view";
import { MarkdownView } from "./markdown-view";

function FileChangeView({
  changes,
}: {
  changes: Array<{ path: string; kind: "add" | "delete" | "update" }>;
}) {
  const kindColors: Record<string, string> = {
    add: "text-green-500 bg-green-500/10",
    delete: "text-red-500 bg-red-500/10",
    update: "text-amber-500 bg-amber-500/10",
  };
  const valid = changes.filter(
    (c): c is { path: string; kind: "add" | "delete" | "update" } =>
      c && typeof c.path === "string" && ["add", "delete", "update"].includes(String(c.kind))
  );
  if (valid.length === 0) return null;

  return (
    <div className="py-1 space-y-0.5">
      {valid.map((change, i) => (
        <div key={i} className="flex items-center gap-2 font-mono text-xs">
          <span
            className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded ${kindColors[change.kind] ?? "text-zinc-500 bg-zinc-500/10"}`}
          >
            {change.kind}
          </span>
          <span className="text-zinc-400">{change.path}</span>
        </div>
      ))}
    </div>
  );
}

function CommandExecutionView({
  command,
  output,
  exitCode,
}: {
  command?: string;
  output?: string;
  exitCode?: number;
}) {
  return (
    <div className="my-1 border border-zinc-800/50 rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-zinc-900/60 font-mono text-xs">
        <span className="text-zinc-500">$ </span>
        <span className="text-zinc-300">{command || "(no command)"}</span>
        {exitCode !== undefined && (
          <span
            className={`ml-2 text-[10px] font-semibold px-1.5 py-0.5 rounded ${
              exitCode === 0
                ? "bg-green-500/10 text-green-500"
                : "bg-red-500/10 text-red-500"
            }`}
          >
            exit {exitCode}
          </span>
        )}
      </div>
      {output && (
        <pre className="p-3 bg-zinc-950/80 font-mono text-[11px] text-zinc-600 overflow-auto max-h-[300px] whitespace-pre-wrap border-t border-zinc-800/50">
          {output}
        </pre>
      )}
    </div>
  );
}

export function EventView({ event }: { event: ThreadEvent }) {
  switch (event.type) {
    case "system":
      return (
        <div className="text-xs text-zinc-700 italic py-1">
          Session initialized: {event.session_id ?? "unknown"}
        </div>
      );

    case "assistant":
      if (!event.message?.content || !Array.isArray(event.message.content)) {
        return null;
      }
      return (
        <div className="py-1 space-y-0.5">
          {event.message.content.map((block, i) => (
            <ContentBlockView key={i} block={block} />
          ))}
        </div>
      );

    case "tool":
      if (!event.content || !Array.isArray(event.content)) {
        return null;
      }
      return (
        <div className="py-0.5 space-y-0.5">
          {event.content.map((block, i) => (
            <ContentBlockView key={i} block={block} />
          ))}
        </div>
      );

    case "result":
      return event.result ? (
        <div className="py-1">
          <div className="text-sm leading-relaxed text-zinc-300">
            <MarkdownView text={event.result} />
          </div>
        </div>
      ) : null;

    case "error":
      return (
        <div className="py-1 px-3 my-1 bg-red-500/8 border border-red-500/15 rounded-lg text-[13px] text-red-300">
          {event.error || (typeof event.message === "string" ? event.message : "Unknown error")}
        </div>
      );

    case "thread.started":
      return (
        <div className="text-xs text-zinc-700 italic py-1">
          Codex thread started: {event.thread_id ?? "unknown"}
        </div>
      );

    case "item.completed":
      return (
        <div className="py-1">
          <div className="text-sm leading-relaxed text-zinc-300">
            <MarkdownView text={event.item?.text ?? ""} />
          </div>
        </div>
      );

    case "file_change": {
      const changes = Array.isArray(event.changes) ? event.changes : [];
      return <FileChangeView changes={changes} />;
    }

    case "command_execution":
      return (
        <CommandExecutionView
          command={event.command}
          output={event.aggregated_output}
          exitCode={event.exit_code}
        />
      );

    case "reasoning":
      return <ThinkingView text={event.text} />;

    case "raw":
      return (
        <ThinkingView
          text={event.text}
          label="Raw output"
          warning="Raw model/tool output can include noisy or sensitive context."
        />
      );

    default:
      return null;
  }
}
