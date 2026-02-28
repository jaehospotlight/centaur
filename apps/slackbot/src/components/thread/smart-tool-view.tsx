"use client";

import { useState } from "react";
import type { ToolUseBlock } from "@/lib/types";
import { DiffView } from "./diff-view";

function TerminalView({
  command,
  output,
  exitCode,
}: {
  command: string;
  output?: string;
  exitCode?: number;
}) {
  const [showFull, setShowFull] = useState(false);
  const lines = output?.split("\n") ?? [];
  const truncated = lines.length > 30 && !showFull;
  const displayLines = truncated ? lines.slice(0, 30) : lines;

  return (
    <div className="border-t border-zinc-800/50">
      <div className="px-3 py-2 font-mono text-xs">
        <span className="text-zinc-500">$ </span>
        <span className="text-zinc-300">{command}</span>
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
        <pre className="px-3 pb-2 font-mono text-[11px] text-zinc-600 overflow-auto max-h-[300px] whitespace-pre-wrap">
          {displayLines.join("\n")}
        </pre>
      )}
      {truncated && (
        <button
          type="button"
          onClick={() => setShowFull(true)}
          className="px-3 pb-2 text-[11px] text-zinc-700 hover:text-zinc-500 transition-colors duration-200 cursor-pointer"
        >
          show full output ({lines.length} lines)
        </button>
      )}
    </div>
  );
}

function NewFileView({
  path,
  content,
}: {
  path: string;
  content: string;
}) {
  const [showFull, setShowFull] = useState(false);
  const lines = content.split("\n");
  const truncated = lines.length > 30 && !showFull;
  const displayLines = truncated ? lines.slice(0, 30) : lines;

  return (
    <div className="border-t border-zinc-800/50 border-l-2 border-l-green-500/50">
      <div className="px-3 py-1.5 flex items-center gap-2 border-b border-zinc-800/50">
        <span className="font-mono text-[11px] text-zinc-400">{path}</span>
        <span className="text-[10px] font-semibold text-green-500">+ new file</span>
      </div>
      <pre className="p-3 font-mono text-[11px] text-zinc-500 overflow-auto max-h-[400px]">
        {displayLines.map((line, i) => (
          <span key={i} className="block">
            <span className="inline-block w-8 text-right text-zinc-700 select-none mr-3">
              {i + 1}
            </span>
            {line}
          </span>
        ))}
      </pre>
      {truncated && (
        <button
          type="button"
          onClick={() => setShowFull(true)}
          className="px-3 pb-2 text-[11px] text-zinc-700 hover:text-zinc-500 transition-colors duration-200 cursor-pointer"
        >
          show all {lines.length} lines
        </button>
      )}
    </div>
  );
}

function FilePreview({ path }: { path: string }) {
  return (
    <div className="border-t border-zinc-800/50 px-3 py-1.5">
      <span className="font-mono text-[11px] text-zinc-400">{path}</span>
    </div>
  );
}

function SearchView({
  pattern,
  path,
}: {
  pattern: string;
  path?: string;
}) {
  return (
    <div className="border-t border-zinc-800/50 px-3 py-1.5 font-mono text-[11px]">
      <span className="text-zinc-500">pattern: </span>
      <span className="text-amber-500">{pattern}</span>
      {path && (
        <>
          <span className="text-zinc-700 mx-1.5">in</span>
          <span className="text-zinc-400">{path}</span>
        </>
      )}
    </div>
  );
}

function GenericToolView({ input }: { input: Record<string, unknown> }) {
  return (
    <div className="border-t border-zinc-800/50">
      <pre className="p-3 font-mono text-xs text-zinc-600 overflow-auto max-h-[300px] whitespace-pre-wrap break-all">
        {JSON.stringify(input, null, 2)}
      </pre>
    </div>
  );
}

export function SmartToolView({ block }: { block: ToolUseBlock }) {
  const input = block.input as Record<string, string | number | undefined>;

  switch (block.name) {
    case "str_replace":
      return (
        <DiffView
          path={String(input.path ?? "")}
          old={String(input.old ?? "")}
          new={String(input.new ?? "")}
        />
      );
    case "write_file":
      return (
        <NewFileView
          path={String(input.path ?? "")}
          content={String(input.content ?? "")}
        />
      );
    case "read_file":
      return <FilePreview path={String(input.path ?? "")} />;
    case "shell":
      return <TerminalView command={String(input.command ?? "")} />;
    case "grep_search":
      return (
        <SearchView
          pattern={String(input.pattern ?? "")}
          path={input.path ? String(input.path) : undefined}
        />
      );
    default:
      return <GenericToolView input={block.input} />;
  }
}
