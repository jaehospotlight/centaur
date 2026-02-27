import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { readFileSync, existsSync } from "fs";
import { join } from "path";
import { readAgentPrompt } from "./tools/lib/pi-spawn";
import { interpolatePromptVars } from "./tools/lib/interpolate";

export default function (pi: ExtensionAPI) {
  // Read system prompt — try agents file first, fall back to ~/AGENTS.md
  let body = readAgentPrompt("prompt.amp.system.md");
  if (!body) {
    const home = process.env.HOME || "/home/agent";
    const candidates = [join(home, "AGENTS.md"), join(process.cwd(), "AGENTS.md")];
    for (const p of candidates) {
      if (existsSync(p)) {
        try {
          body = readFileSync(p, "utf-8");
          break;
        } catch {}
      }
    }
  }

  pi.on("before_agent_start", async (event, ctx) => {
    if (!body) return { systemPrompt: event.systemPrompt };

    const interpolated = interpolatePromptVars(body);
    return { systemPrompt: event.systemPrompt + "\n\n" + interpolated };
  });
}
