"use client";

import { PHASES, type Turn } from "@/lib/types";
import { cn } from "@/lib/utils";

function extractPhases(turns: Turn[]): Set<string> {
  const phases = new Set<string>();
  for (const turn of turns) {
    const match = (turn.user_message ?? "").match(/^\[(\w+)\]/);
    if (match) phases.add(match[1].toLowerCase());
  }
  return phases;
}

function getActivePhase(turns: Turn[]): string | null {
  for (let i = turns.length - 1; i >= 0; i--) {
    const match = (turns[i].user_message ?? "").match(/^\[(\w+)\]/);
    if (match) return match[1].toLowerCase();
  }
  return null;
}

export function PhaseProgress({ turns }: { turns: Turn[] }) {
  const completedPhases = extractPhases(turns);
  const activePhase = getActivePhase(turns);

  return (
    <div className="flex items-center gap-0.5 overflow-x-auto">
      {PHASES.map((phase, i) => {
        const isActive = phase === activePhase;
        const isDone = completedPhases.has(phase) && !isActive;
        const isFuture = !completedPhases.has(phase) && !isActive;

        return (
          <div key={phase} className="flex items-center gap-0.5">
            {i > 0 && (
              <span
                className={cn(
                  "text-[9px] mx-0.5",
                  isFuture ? "text-zinc-800" : "text-zinc-700",
                )}
              >
                &gt;
              </span>
            )}
            <div className="flex items-center gap-1">
              {isActive && (
                <span className="size-[6px] rounded-full bg-amber-500 animate-pulse-dot shrink-0" />
              )}
              {isDone && (
                <span className="text-[9px] text-zinc-600 shrink-0">&#10003;</span>
              )}
              <span
                className={cn(
                  "text-[10px] font-medium uppercase tracking-wider whitespace-nowrap transition-colors duration-200",
                  isActive && "text-zinc-300",
                  isDone && "text-zinc-600",
                  isFuture && "text-zinc-800",
                )}
              >
                {phase}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
