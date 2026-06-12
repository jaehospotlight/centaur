// Interactive terminal chat driving a real harness CLI (Codex, Claude Code,
// or Amp) through harness-server, rendered via the AI SDK UI message stream.
//
// Usage (requires Node >= 23.6 for type stripping, and `harness-server` plus
// the harness CLI on PATH or HARNESS_SERVER_BIN/CLAUDE_BIN/... set):
//
//   node examples/chat.ts claude-code "what files are in this directory?"
//   node examples/chat.ts codex "summarize the README"
import { readUIMessageStream } from "ai";
import { HarnessChatTransport, type HarnessName } from "../src/index.ts";

const [harness = "claude-code", ...promptParts] = process.argv.slice(2);
const prompt = promptParts.join(" ") || "Say hello and tell me which harness you are.";

const transport = new HarnessChatTransport({
  harness: harness as HarnessName,
  threadCwd: process.cwd(),
  onStderr: (line) => process.stderr.write(`[harness-server] ${line}\n`),
});

const stream = await transport.sendMessages({
  trigger: "submit-message",
  chatId: "example",
  messageId: undefined,
  messages: [{ id: "u-1", role: "user", parts: [{ type: "text", text: prompt }] }],
  abortSignal: undefined,
});

let lastText = "";
const announcedTools = new Set<string>();
for await (const message of readUIMessageStream({ stream })) {
  for (const part of message.parts) {
    if (
      part.type === "dynamic-tool" &&
      part.input !== undefined &&
      !announcedTools.has(part.toolCallId)
    ) {
      announcedTools.add(part.toolCallId);
      console.log(`\n[tool ${part.toolName}]`, JSON.stringify(part.input));
    }
  }
  const text = message.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");
  process.stdout.write(text.slice(lastText.length));
  lastText = text;
}
process.stdout.write("\n");

await transport.close();
