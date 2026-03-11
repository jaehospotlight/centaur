"use client";

import { useEffect, useState } from "react";
import { Suggestions, Suggestion } from "@/components/ai-elements/suggestion";
import { useHaptics } from "@/components/haptics-provider";
import { SurfaceBar } from "@/components/ui/surface-bar";
import { cn } from "@/lib/utils";

type ChipAction = {
  label: string;
  value: string;
  variant?: "default" | "destructive" | "outline";
};

type QuickActionChipsProps = {
  threadState: string;
  onAction: (value: string) => void;
  className?: string;
};

const CHIP_SETS: Record<string, ChipAction[]> = {
  error: [
    { label: "Run again", value: "retry", variant: "default" },
    { label: "Retry more thoroughly", value: "retry-thoroughly", variant: "default" },
  ],
  stopped: [
    { label: "Resume", value: "resume", variant: "default" },
  ],
};

export function QuickActionChips({ threadState, onAction, className }: QuickActionChipsProps) {
  const { trigger } = useHaptics();
  const normalizedState = threadState === "working" ? "running" : threadState;
  const chips = CHIP_SETS[normalizedState];
  const [renderedChips, setRenderedChips] = useState<ChipAction[] | null>(chips ?? null);
  const [visibility, setVisibility] = useState<"open" | "closed">(chips?.length ? "open" : "closed");

  useEffect(() => {
    if (chips && chips.length > 0) {
      setRenderedChips(chips);
      setVisibility("open");
      return;
    }
    if (!renderedChips) return;
    setVisibility("closed");
    const timer = window.setTimeout(() => setRenderedChips(null), 180);
    return () => window.clearTimeout(timer);
  }, [chips, renderedChips]);

  if (!renderedChips || renderedChips.length === 0) return null;

  return (
    <SurfaceBar
      data-state={visibility}
      className={cn(
        "border-t border-border/70 px-2.5 py-2",
        "data-[state=open]:animate-in data-[state=open]:slide-in-from-bottom-2 data-[state=open]:fade-in data-[state=open]:duration-base",
        "data-[state=closed]:animate-out data-[state=closed]:slide-out-to-bottom-2 data-[state=closed]:fade-out data-[state=closed]:duration-fast",
        className,
      )}
    >
      <div className="mx-auto flex max-w-content-max flex-wrap items-center gap-2 rounded-[var(--radius-surface)] border border-border/70 bg-card/45 px-3 py-2.5 shadow-chips">
        <span className="ui-caption font-medium text-muted-foreground">
          Quick actions
        </span>
        <Suggestions className="min-w-0 flex-1 rounded-none border-0 bg-transparent p-0 shadow-none">
        {renderedChips.map((chip) => (
          <Suggestion
            key={chip.value}
            suggestion={chip.value}
            variant={chip.variant ?? "outline"}
            onClick={(value) => { trigger("medium"); onAction(value); }}
            className={cn(
              "min-h-touch rounded-full border-border/70 bg-background/70 px-3 text-sm",
              chip.variant === "default" && "bg-primary/12 text-primary hover:bg-primary/16",
            )}
          >
            {chip.label}
          </Suggestion>
        ))}
        </Suggestions>
      </div>
    </SurfaceBar>
  );
}
