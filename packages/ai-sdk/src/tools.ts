import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { tool, type ToolSet } from "ai";
import { z } from "zod";

/**
 * Default toolset for the bridge agent. The shell tool is named `Bash` on
 * purpose: harness-server's turn normalizer projects tool calls with that
 * name to first-class `commandExecution` thread items, so AI SDK shell runs
 * render exactly like Claude Code's.
 */
export function defaultTools(cwd: string): ToolSet {
  return {
    Bash: tool({
      description:
        "Run a shell command in the workspace and return its output. Use for inspecting files, running builds, and any filesystem work.",
      inputSchema: z.object({
        command: z.string().describe("The shell command to run"),
      }),
      execute: async ({ command }) => {
        const result = spawnSync("sh", ["-c", command], {
          cwd,
          encoding: "utf8",
          timeout: 120_000,
          maxBuffer: 4 * 1024 * 1024,
        });
        return {
          stdout: result.stdout ?? "",
          stderr: result.error ? String(result.error) : (result.stderr ?? ""),
          exitCode: result.status ?? 1,
        };
      },
    }),
    ReadFile: tool({
      description: "Read a text file from the workspace.",
      inputSchema: z.object({
        path: z.string().describe("File path, relative to the workspace root"),
      }),
      execute: async ({ path }) => readFileSync(resolve(cwd, path), "utf8").slice(0, 64_000),
    }),
  };
}
