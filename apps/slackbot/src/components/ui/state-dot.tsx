import { cn } from "@/lib/utils";
import { STATE_DOT_COLORS } from "@/lib/constants";

export function StateDot({ state, className }: { state: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "size-[6px] rounded-full shrink-0 transition-colors duration-200",
        STATE_DOT_COLORS[state] ?? "bg-zinc-600",
        state === "working" && "animate-pulse-dot",
        className
      )}
    />
  );
}
