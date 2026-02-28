"use client";

import { useMemo } from "react";
import { diffLines } from "diff";

export function DiffView({
  path,
  old: oldText,
  new: newText,
}: {
  path: string;
  old: string;
  new: string;
}) {
  const changes = useMemo(() => diffLines(oldText, newText), [oldText, newText]);

  return (
    <div className="border-t border-zinc-800/50">
      <div className="px-3 py-1.5 text-[11px] font-mono text-zinc-400 border-b border-zinc-800/50">
        {path}
      </div>
      <pre className="p-3 font-mono text-xs overflow-auto max-h-[400px]">
        {changes.map((part, i) => {
          if (part.added) {
            return (
              <span key={i} className="block bg-green-950/50 text-green-300">
                {part.value
                  .split("\n")
                  .filter((l, idx, arr) => idx < arr.length - 1 || l)
                  .map((line, j) => (
                    <span key={j} className="block">
                      + {line}
                    </span>
                  ))}
              </span>
            );
          }
          if (part.removed) {
            return (
              <span key={i} className="block bg-red-950/50 text-red-300">
                {part.value
                  .split("\n")
                  .filter((l, idx, arr) => idx < arr.length - 1 || l)
                  .map((line, j) => (
                    <span key={j} className="block">
                      - {line}
                    </span>
                  ))}
              </span>
            );
          }
          return (
            <span key={i} className="block text-zinc-600">
              {part.value
                .split("\n")
                .filter((l, idx, arr) => idx < arr.length - 1 || l)
                .map((line, j) => (
                  <span key={j} className="block">
                    {"  "}{line}
                  </span>
                ))}
            </span>
          );
        })}
      </pre>
    </div>
  );
}
