"use client";

import React from "react";
import { useHaptics } from "@/components/haptics-provider";
import { Button } from "@/components/ui/button";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { cn } from "@/lib/utils";
import { THREAD_STATUS_FILTER_OPTIONS, type VisibleThreadStatusFilter } from "@/components/thread/thread-ui-constants";

type ThreadStatusTabsProps = {
  value: VisibleThreadStatusFilter;
  counts: Record<VisibleThreadStatusFilter, number>;
  onChange: (next: VisibleThreadStatusFilter) => void;
  density?: "compact" | "comfortable";
  className?: string;
};

export function ThreadStatusTabs({
  value,
  counts,
  onChange,
  density = "comfortable",
  className,
}: ThreadStatusTabsProps) {
  const compact = density === "compact";
  const { trigger } = useHaptics();

  return (
    <div
      role="group"
      aria-label="Thread filters"
      className={cn(
        "thread-surface-soft flex w-full items-center gap-1 rounded-[var(--radius-surface)] p-1",
        className,
      )}
    >
      {THREAD_STATUS_FILTER_OPTIONS.map((option) => {
        const active = value === option.id;
        return (
          <Button
            key={option.id}
            type="button"
            onClick={() => {
              if (!active) trigger("selection");
              onChange(option.id);
            }}
            variant="ghost"
            aria-pressed={active}
            className={cn(
              "inline-flex min-h-10 flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-control)] px-3 py-2 text-sm font-medium transition-colors duration-[var(--dur-fast)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
              active
                ? "border border-border/70 bg-background/90 text-foreground shadow-ring-subtle"
                : "border border-transparent text-muted-foreground hover:bg-accent/35 hover:text-foreground",
            )}
          >
            <span>{compact ? option.shortLabel : option.label}</span>
            <span className={cn(
              "text-detail tabular-nums",
              active ? "text-foreground/60" : "text-muted-foreground/60",
            )}>
              <AnimatedNumber value={counts[option.id]} />
            </span>
          </Button>
        );
      })}
    </div>
  );
}
