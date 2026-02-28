"use client";

import { ChevronRight } from "lucide-react";

export function ThinkingDivider({ text, durationS }: { text: string; durationS?: number }) {
  if (!text.trim()) return null;
  return (
    <details className="group step-item">
      <summary className="list-none cursor-pointer select-none flex items-center gap-1.5 text-xs text-muted-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3 transition-transform group-open:rotate-90" />
        Thought{durationS ? ` for ${durationS}s` : ""}
      </summary>
      <pre className="mt-1 rounded-sm bg-background p-3 max-h-[220px] overflow-auto whitespace-pre-wrap font-mono text-xs italic text-muted-foreground">
        {text}
      </pre>
    </details>
  );
}
