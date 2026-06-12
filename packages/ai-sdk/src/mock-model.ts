import type { LanguageModelV3StreamPart } from "@ai-sdk/provider";
import { simulateReadableStream, type LanguageModel } from "ai";
import { MockLanguageModelV3 } from "ai/test";

const usage = {
  inputTokens: { total: 1, noCache: 1, cacheRead: undefined, cacheWrite: undefined },
  outputTokens: { total: 1, text: 1, reasoning: undefined },
  totalTokens: 2,
};

const toolCallStep: LanguageModelV3StreamPart[] = [
  { type: "stream-start", warnings: [] },
  { type: "text-start", id: "t1" },
  { type: "text-delta", id: "t1", delta: "Let me check." },
  { type: "text-end", id: "t1" },
  {
    type: "tool-call",
    toolCallId: "call_1",
    toolName: "Bash",
    input: JSON.stringify({ command: "printf mock-tool-ok" }),
  },
  { type: "finish", finishReason: { unified: "tool-calls", raw: "tool-calls" }, usage },
];

const finalAnswerStep: LanguageModelV3StreamPart[] = [
  { type: "stream-start", warnings: [] },
  { type: "text-start", id: "t2" },
  { type: "text-delta", id: "t2", delta: "The command printed: " },
  { type: "text-delta", id: "t2", delta: "mock-tool-ok" },
  { type: "text-end", id: "t2" },
  { type: "finish", finishReason: { unified: "stop", raw: "stop" }, usage },
];

/**
 * Deterministic two-step agent scenario (shell tool call, then a final
 * answer) for offline end-to-end tests of the harness-server pipeline.
 */
export function mockModel(): LanguageModel {
  // Function form rather than the array form: MockLanguageModelV3's array
  // indexing skips entry 0 (it indexes by call count after recording the
  // call), and a function builds a fresh single-use stream per call.
  let call = 0;
  const steps = [toolCallStep, finalAnswerStep];
  return new MockLanguageModelV3({
    modelId: "mock",
    doStream: async () => {
      const chunks = steps[call++];
      if (!chunks) throw new Error("mock model exhausted: only two steps are scripted");
      return { stream: simulateReadableStream({ chunks }) };
    },
  });
}
