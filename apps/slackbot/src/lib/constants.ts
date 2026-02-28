export const HARNESS_COLORS: Record<string, { bg: string; text: string }> = {
  amp: { bg: "bg-cyan-500/10", text: "text-cyan-400" },
  "claude-code": { bg: "bg-violet-500/10", text: "text-violet-400" },
  codex: { bg: "bg-emerald-500/10", text: "text-emerald-400" },
  "pi-mono": { bg: "bg-blue-500/10", text: "text-blue-400" },
  engineer: { bg: "bg-orange-500/10", text: "text-orange-400" },
};

export const STATE_DOT_COLORS: Record<string, string> = {
  running: "bg-green-500",
  idle: "bg-zinc-600",
  stopped: "bg-zinc-500",
  working: "bg-amber-500",
  waiting: "bg-violet-500",
  error: "bg-red-500",
};

export const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
