import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import type { Harness } from "@/lib/types";
import { HARNESS_COLORS } from "@/lib/constants";

export const harnessBadgeVariants = cva(
  "text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded",
  {
    variants: {
      harness: {
        amp: "bg-cyan-500/10 text-cyan-400",
        "claude-code": "bg-violet-500/10 text-violet-400",
        codex: "bg-emerald-500/10 text-emerald-400",
        "pi-mono": "bg-blue-500/10 text-blue-400",
        engineer: "bg-orange-500/10 text-orange-400",
      },
    },
    defaultVariants: {
      harness: "amp",
    },
  },
);

interface HarnessBadgeProps extends React.HTMLAttributes<HTMLSpanElement>, Omit<VariantProps<typeof harnessBadgeVariants>, "harness"> {
  harness: Harness | string;
}

export function HarnessBadge({ harness, className, ...props }: HarnessBadgeProps) {
  const isKnownHarness = harness in HARNESS_COLORS;

  return (
    <span
      className={cn(
        harnessBadgeVariants({ harness: isKnownHarness ? (harness as Harness) : undefined }),
        !isKnownHarness && "bg-zinc-800 text-zinc-400",
        className
      )}
      {...props}
    >
      {harness}
    </span>
  );
}
