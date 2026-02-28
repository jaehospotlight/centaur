"use client";

import { useMemo, useState } from "react";
import { diffLines } from "diff";
import { Badge } from "@/components/ui/badge";

const LANGUAGE_CLASSES: Record<string, string> = {
  ts: "bg-blue-500/10 text-blue-400",
  tsx: "bg-blue-500/10 text-blue-400",
  js: "bg-yellow-500/10 text-yellow-400",
  jsx: "bg-yellow-500/10 text-yellow-400",
  py: "bg-green-500/10 text-green-400",
  css: "bg-purple-500/10 text-purple-400",
  json: "bg-amber-500/10 text-amber-400",
  md: "bg-secondary text-muted-foreground",
  sh: "bg-green-500/10 text-green-400",
};

export function DiffCard({
  file,
  lang,
  oldStr,
  newStr,
}: {
  file: string;
  lang: string;
  oldStr: string;
  newStr: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const chunks = useMemo(() => diffLines(oldStr, newStr), [oldStr, newStr]);
  const canToggle = chunks.length > 10;
  const hiddenCount = Math.max(0, chunks.length - 10);
  const visibleChunks = expanded ? chunks : chunks.slice(0, 10);

  return (
    <div className="step-item rounded-sm border border-border bg-card overflow-hidden">
      <div className="px-3 py-2 border-b border-border flex items-center gap-2">
        <Badge className={LANGUAGE_CLASSES[lang] ?? "bg-secondary text-muted-foreground"}>{lang}</Badge>
        <span className="font-mono text-xs text-foreground truncate">{file}</span>
      </div>
      <pre className="p-3 text-[11px] font-mono overflow-auto max-h-[360px]">
        {visibleChunks.map((chunk, i) => {
          const tone = chunk.added
            ? "bg-green-500/10 text-green-300"
            : chunk.removed
              ? "bg-red-500/10 text-red-300"
              : "text-muted-foreground";
          const prefix = chunk.added ? "+" : chunk.removed ? "-" : " ";
          return (
            <span key={i} className={`block ${tone}`}>
              {chunk.value
                .split("\n")
                .filter((line, index, arr) => index < arr.length - 1 || line)
                .map((line, lineIndex) => (
                  <span key={lineIndex} className="block">
                    {prefix} {line}
                  </span>
                ))}
            </span>
          );
        })}
      </pre>
      {canToggle && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          className="w-full border-t border-border px-3 py-1.5 text-left text-xs text-muted-foreground hover:text-foreground cursor-pointer"
        >
          {expanded ? "Show less context" : `Show ${hiddenCount} hidden diff blocks`}
        </button>
      )}
    </div>
  );
}
