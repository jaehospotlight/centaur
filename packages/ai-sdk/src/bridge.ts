#!/usr/bin/env node
// Bridge binary spawned by `harness-server ai-sdk`: runs a Vercel AI SDK
// agent loop and speaks Claude-CLI-compatible stream-json on stdio.
//
// Config: AISDK_MODEL / --model (default claude-sonnet-4-6; "mock" runs a
// scripted offline model for e2e tests), ANTHROPIC_API_KEY for real runs.
import { existsSync, readFileSync } from "node:fs";
import { createInterface } from "node:readline";
import { anthropic } from "@ai-sdk/anthropic";
import type { LanguageModel } from "ai";
import { AiSdkBridge } from "./bridge-core.ts";
import { mockModel } from "./mock-model.ts";
import { defaultTools } from "./tools.ts";

function argValue(flag: string): string | undefined {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

const sessionId =
  argValue("--resume") ?? argValue("--session-id") ?? `aisdk-${process.pid}`;
const modelId = argValue("--model") || process.env.AISDK_MODEL || "claude-sonnet-4-6";
const cwd = process.cwd();

function resolveModel(id: string): LanguageModel {
  if (id === "mock") return mockModel();
  return anthropic(id);
}

function systemPrompt(): string {
  let prompt = `You are a coding agent operating in the workspace ${cwd}. Use the available tools to inspect and modify the workspace; reply concisely.`;
  const agentsMd = `${cwd}/AGENTS.md`;
  if (existsSync(agentsMd)) {
    prompt += `\n\n${readFileSync(agentsMd, "utf8")}`;
  }
  return prompt;
}

const emit = (line: Record<string, unknown>) =>
  process.stdout.write(`${JSON.stringify(line)}\n`);

emit({ type: "system", subtype: "init", session_id: sessionId });

const bridge = new AiSdkBridge({
  model: resolveModel(modelId),
  tools: defaultTools(cwd),
  sessionId,
  system: systemPrompt(),
  emit,
});

createInterface({ input: process.stdin }).on("line", (line) =>
  bridge.handleStdinLine(line),
);
