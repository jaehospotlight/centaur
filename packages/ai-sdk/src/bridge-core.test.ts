import { describe, expect, it } from "vitest";
import { tool } from "ai";
import { z } from "zod";
import { AiSdkBridge } from "./bridge-core.ts";
import { mockModel } from "./mock-model.ts";

const fakeBash = tool({
  description: "fake shell",
  inputSchema: z.object({ command: z.string() }),
  execute: async ({ command }) => ({
    stdout: `ran: ${command}\n`,
    stderr: "",
    exitCode: 0,
  }),
});

function userLine(text: string): string {
  return JSON.stringify({
    type: "user",
    message: { role: "user", content: [{ type: "text", text }] },
  });
}

async function runTurn(text: string) {
  const lines: Array<Record<string, unknown>> = [];
  const bridge = new AiSdkBridge({
    model: mockModel(),
    tools: { Bash: fakeBash },
    sessionId: "test-session",
    emit: (line) => lines.push(line),
  });
  bridge.handleStdinLine(userLine(text));
  await bridge.idle();
  return lines;
}

describe("AiSdkBridge", () => {
  it("emits a claude-compatible stream for a tool-using turn", async () => {
    const lines = await runTurn("run the tool");

    const kinds = lines.map((line) =>
      line.type === "stream_event"
        ? `stream_event:${(line.event as { type: string }).type}`
        : (line.type as string),
    );
    expect(kinds).toEqual([
      "stream_event:message_start",
      "stream_event:content_block_start",
      "stream_event:content_block_delta",
      "stream_event:content_block_stop",
      "assistant",
      "user",
      "stream_event:message_start",
      "stream_event:content_block_start",
      "stream_event:content_block_delta",
      "stream_event:content_block_delta",
      "stream_event:content_block_stop",
      "assistant",
      "result",
    ]);

    const firstAssistant = lines[4] as {
      message: { id: string; stop_reason: string; content: Array<Record<string, unknown>> };
    };
    expect(firstAssistant.message.stop_reason).toBe("tool_use");
    expect(firstAssistant.message.content).toEqual([
      { type: "text", text: "Let me check." },
      {
        type: "tool_use",
        id: "call_1",
        name: "Bash",
        input: { command: "printf mock-tool-ok" },
      },
    ]);

    const toolResult = lines[5] as {
      message: { content: Array<Record<string, unknown>> };
      tool_use_result: Record<string, unknown>;
    };
    expect(toolResult.message.content[0]).toEqual({
      type: "tool_result",
      tool_use_id: "call_1",
      content: "ran: printf mock-tool-ok\n",
      is_error: false,
    });
    expect(toolResult.tool_use_result).toEqual({
      stdout: "ran: printf mock-tool-ok\n",
      stderr: "",
      exit_code: 0,
    });

    const finalAssistant = lines[11] as {
      message: { stop_reason: string; content: Array<Record<string, unknown>> };
    };
    expect(finalAssistant.message.stop_reason).toBe("end_turn");
    expect(finalAssistant.message.content).toEqual([
      { type: "text", text: "The command printed: mock-tool-ok" },
    ]);

    expect(lines[12]).toEqual({ type: "result", subtype: "success" });
  });

  it("reports model errors as an error result instead of crashing", async () => {
    const lines: Array<Record<string, unknown>> = [];
    const bridge = new AiSdkBridge({
      model: mockModel(),
      tools: {},
      sessionId: "test-session",
      emit: (line) => lines.push(line),
    });
    // The mock scripts two streams; a third turn exhausts it and throws.
    for (let i = 0; i < 3; i++) {
      bridge.handleStdinLine(userLine(`turn ${i}`));
      await bridge.idle();
    }
    const last = lines.at(-1) as { type: string; is_error?: boolean };
    expect(last.type).toBe("result");
    expect(last.is_error).toBe(true);
  });
});
