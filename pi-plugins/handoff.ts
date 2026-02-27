import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";

const HANDOFF_THRESHOLD = 0.85;

export default function (pi: ExtensionAPI) {
  let storedHandoffPrompt: string | null = null;
  let handoffPending = false;
  let generating = false;
  let parentSessionFile: string | null = null;

  // Cancel built-in compaction
  pi.on("session_before_compact", async () => ({ cancel: true }));

  // Monitor context usage after each agent turn
  pi.on("agent_end", async (_event, ctx) => {
    if (handoffPending || generating) return;
    const usage = ctx.getContextUsage();
    if (!usage || usage.percent === null) return;
    if (usage.percent < HANDOFF_THRESHOLD * 100) return;

    generating = true;
    try {
      const pct = Math.round(usage.percent);
      ctx.ui.notify(
        `Context at ${pct}% — generating handoff prompt. Use /handoff when ready.`,
        "warning",
      );

      // Ask the agent to produce a handoff summary
      const summary = await ctx.generateText(
        "Produce a concise handoff prompt summarizing: 1) what was accomplished, " +
          "2) current state of the work, 3) what remains to be done. " +
          "Include relevant file paths, decisions made, and any blockers. " +
          "Format as a prompt that a fresh agent session can act on immediately.",
      );

      storedHandoffPrompt = summary;
      handoffPending = true;

      // Stage /handoff in the editor so the user can trigger it
      ctx.ui.stageCommand("/handoff");
    } finally {
      generating = false;
    }
  });

  // /handoff command
  pi.registerCommand("handoff", {
    description: "Create a new session with context from the current one",
    handler: async (args, ctx) => {
      const prompt =
        args ||
        storedHandoffPrompt ||
        "Continue the work from the previous session.";

      const usage = ctx.getContextUsage();
      const pct = usage?.percent ? Math.round(usage.percent) : null;

      if (pct !== null && pct < 50 && !storedHandoffPrompt) {
        const ok = await ctx.ui.confirm(
          `Context is only ${pct}% full. Handoff anyway?`,
        );
        if (!ok) return;
      }

      ctx.ui.notify(
        `Handing off session${pct !== null ? ` (${pct}% context used)` : ""}...`,
        "info",
      );

      await ctx.newSession({
        prompt: [
          "# Handoff from previous session",
          "",
          pct !== null
            ? `Previous session was at ${pct}% context capacity.`
            : "Previous session context was full.",
          "",
          prompt,
          "",
          "Continue the work from where the previous session left off.",
        ].join("\n"),
      });

      // Reset state
      storedHandoffPrompt = null;
      handoffPending = false;
    },
  });

  // handoff tool for agent invocation
  pi.registerTool({
    name: "handoff",
    label: "Handoff",
    description: "Hand off work to a new session when context is getting full",
    parameters: Type.Object({
      goal: Type.String({
        description: "What should continue in the new session",
      }),
    }),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      const usage = ctx.getContextUsage();
      const pct = usage?.percent ? Math.round(usage.percent) : null;

      const prompt = [
        "# Handoff from previous session",
        "",
        pct !== null
          ? `Previous session was at ${pct}% context capacity.`
          : "Previous session context was full.",
        "",
        params.goal,
        "",
        storedHandoffPrompt
          ? `## Accumulated context\n\n${storedHandoffPrompt}`
          : "",
        "",
        "Continue the work from where the previous session left off.",
      ]
        .filter(Boolean)
        .join("\n");

      await ctx.newSession({ prompt });

      storedHandoffPrompt = null;
      handoffPending = false;

      return { result: "Handoff session created." };
    },
  });
}
