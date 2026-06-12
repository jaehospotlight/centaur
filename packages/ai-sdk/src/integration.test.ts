import { describe, expect, it } from "vitest";
import { readUIMessageStream, type UIMessage, type UIMessageChunk } from "ai";
import type { ServerNotification, Turn } from "@centaur/harness-events";
import { UIMessageChunkConverter } from "./ui-stream.ts";

function turn(status: Turn["status"]): Turn {
  return {
    id: "turn-1",
    items: [],
    itemsView: "full",
    status,
    error: null,
    startedAt: null,
    completedAt: null,
    durationMs: null,
  };
}

// A realistic normalized turn: reasoning, a shell tool call with streamed
// output, then the agent's final message.
const notifications: ServerNotification[] = [
  { method: "turn/started", params: { threadId: "t", turn: turn("inProgress") } },
  {
    method: "item/started",
    params: {
      item: { type: "reasoning", id: "r-1", summary: [], content: [] },
      threadId: "t",
      turnId: "turn-1",
      startedAtMs: 0,
    },
  },
  {
    method: "item/reasoning/textDelta",
    params: { threadId: "t", turnId: "turn-1", itemId: "r-1", delta: "checking files", contentIndex: 0 },
  },
  {
    method: "item/completed",
    params: {
      item: { type: "reasoning", id: "r-1", summary: [], content: ["checking files"] },
      threadId: "t",
      turnId: "turn-1",
      completedAtMs: 1,
    },
  },
  {
    method: "item/started",
    params: {
      item: {
        type: "commandExecution",
        id: "cmd-1",
        command: "ls",
        cwd: "/repo",
        processId: null,
        status: "inProgress",
        aggregatedOutput: null,
        exitCode: null,
      },
      threadId: "t",
      turnId: "turn-1",
      startedAtMs: 1,
    },
  },
  {
    method: "item/commandExecution/outputDelta",
    params: { threadId: "t", turnId: "turn-1", itemId: "cmd-1", delta: "README.md\n" },
  },
  {
    method: "item/completed",
    params: {
      item: {
        type: "commandExecution",
        id: "cmd-1",
        command: "ls",
        cwd: "/repo",
        processId: null,
        status: "completed",
        aggregatedOutput: "README.md\n",
        exitCode: 0,
      },
      threadId: "t",
      turnId: "turn-1",
      completedAtMs: 2,
    },
  },
  {
    method: "item/started",
    params: {
      item: { type: "agentMessage", id: "msg-1", text: "", phase: null },
      threadId: "t",
      turnId: "turn-1",
      startedAtMs: 2,
    },
  },
  {
    method: "item/agentMessage/delta",
    params: { threadId: "t", turnId: "turn-1", itemId: "msg-1", delta: "One file: README.md" },
  },
  {
    method: "item/completed",
    params: {
      item: { type: "agentMessage", id: "msg-1", text: "One file: README.md", phase: "final_answer" },
      threadId: "t",
      turnId: "turn-1",
      completedAtMs: 3,
    },
  },
  { method: "turn/completed", params: { threadId: "t", turn: turn("completed") } },
];

describe("AI SDK UI message assembly", () => {
  it("produces chunk sequences the AI SDK state machine accepts", async () => {
    const converter = new UIMessageChunkConverter();
    const chunks = notifications.flatMap((notification) => converter.convert(notification));
    const stream = new ReadableStream<UIMessageChunk>({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(chunk);
        controller.close();
      },
    });

    const errors: unknown[] = [];
    let message: UIMessage | undefined;
    for await (const state of readUIMessageStream({
      stream,
      onError: (error) => errors.push(error),
    })) {
      message = state;
    }

    expect(errors).toEqual([]);
    expect(message).toBeDefined();
    expect(message?.id).toBe("turn-1");
    expect(message?.role).toBe("assistant");

    const types = message?.parts.map((part) => part.type);
    expect(types).toContain("reasoning");
    expect(types).toContain("dynamic-tool");
    expect(types).toContain("text");

    const text = message?.parts.find((part) => part.type === "text");
    expect(text).toMatchObject({ text: "One file: README.md", state: "done" });

    const tool = message?.parts.find((part) => part.type === "dynamic-tool");
    expect(tool).toMatchObject({
      toolName: "shell",
      state: "output-available",
      input: { command: "ls", cwd: "/repo" },
      output: { aggregatedOutput: "README.md\n", exitCode: 0, status: "completed", durationMs: null },
    });
  });
});
