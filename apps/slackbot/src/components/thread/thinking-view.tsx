"use client";

import { useId, useState } from "react";
import { cn } from "@/lib/utils";

export function ThinkingView({
  text,
  label = "Thinking",
  warning,
}: {
  text: string;
  label?: string;
  warning?: string;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  if (!text) return null;

  return (
    <div className="my-1">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={open ? "Collapse thinking" : "Expand thinking"}
        className="flex items-center gap-1.5 text-zinc-600 text-xs italic hover:text-zinc-500 transition-colors duration-150 cursor-pointer"
      >
        <span
          className={cn(
            "inline-block w-0 h-0 transition-transform duration-150",
            "border-t-[4px] border-t-transparent border-b-[4px] border-b-transparent border-l-[5px] border-l-zinc-600",
            open && "rotate-90",
          )}
        />
        {open ? label : `${label}…`}
      </button>
      <div
        id={panelId}
        className="grid transition-[grid-template-rows] duration-150 ease-out"
        style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">
          {warning && (
            <div className="mt-1.5 px-3 py-2 text-[11px] text-zinc-500 border border-zinc-800/50 rounded-lg bg-zinc-950/70">
              {warning}
            </div>
          )}
          <pre className="mt-1.5 text-zinc-500 italic font-mono text-xs p-3 max-h-[200px] overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-950/80">
            {text}
          </pre>
        </div>
      </div>
    </div>
  );
}
