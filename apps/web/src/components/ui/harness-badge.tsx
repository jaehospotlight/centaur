import type { Harness } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { harnessIconFor } from "@/components/icons/harness-icons";

interface HarnessBadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  harness: Harness | string;
}

const HARNESS_STYLES: Record<string, string> = {
  amp: "bg-[color-mix(in_oklab,var(--harness-amp)_12%,transparent)] text-[var(--harness-amp)]",
  "claude-code": "bg-[color-mix(in_oklab,var(--harness-claude)_12%,transparent)] text-[var(--harness-claude)]",
  codex: "bg-[color-mix(in_oklab,var(--harness-codex)_12%,transparent)] text-[var(--harness-codex)]",
  "pi-mono": "bg-[color-mix(in_oklab,var(--harness-pi)_12%,transparent)] text-[var(--harness-pi)]",
  eng: "bg-primary/10 text-primary",
  invest: "bg-amber-500/10 text-amber-400",
  engineer: "bg-primary/10 text-primary",
  legal: "bg-[color-mix(in_oklab,var(--harness-legal)_12%,transparent)] text-[var(--harness-legal)]",
};

export function HarnessBadge({ harness, className, ...props }: HarnessBadgeProps) {
  const Icon = harnessIconFor(harness);
  return (
    <Badge
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-transparent px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]",
        HARNESS_STYLES[harness] ?? "bg-secondary text-muted-foreground",
        className,
      )}
      {...props}
    >
      <Icon className="size-3.5 shrink-0" />
      {harness}
    </Badge>
  );
}
