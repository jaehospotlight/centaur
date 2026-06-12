import { describe, expect, it } from "vitest";
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

function convertAll(notifications: ServerNotification[]) {
  const converter = new UIMessageChunkConverter();
  return notifications.flatMap((notification) => converter.convert(notification));
}

describe("UIMessageChunkConverter", () => {
  it("maps a streamed agent message to a text part", () => {
    const chunks = convertAll([
      { method: "turn/started", params: { threadId: "t", turn: turn("inProgress") } },
      {
        method: "item/started",
        params: {
          item: { type: "agentMessage", id: "item-1", text: "", phase: null },
          threadId: "t",
          turnId: "turn-1",
          startedAtMs: 0,
        },
      },
      {
        method: "item/agentMessage/delta",
        params: { threadId: "t", turnId: "turn-1", itemId: "item-1", delta: "Hel" },
      },
      {
        method: "item/agentMessage/delta",
        params: { threadId: "t", turnId: "turn-1", itemId: "item-1", delta: "lo" },
      },
      {
        method: "item/completed",
        params: {
          item: { type: "agentMessage", id: "item-1", text: "Hello", phase: "final_answer" },
          threadId: "t",
          turnId: "turn-1",
          completedAtMs: 1,
        },
      },
      { method: "turn/completed", params: { threadId: "t", turn: turn("completed") } },
    ]);

    expect(chunks).toEqual([
      { type: "start", messageId: "turn-1" },
      { type: "start-step" },
      { type: "text-start", id: "item-1" },
      { type: "text-delta", id: "item-1", delta: "Hel" },
      { type: "text-delta", id: "item-1", delta: "lo" },
      { type: "text-end", id: "item-1" },
      { type: "finish-step" },
      { type: "finish", finishReason: "stop" },
    ]);
  });

  it("backfills a text part when the message only arrives at completion", () => {
    const chunks = convertAll([
      {
        method: "item/completed",
        params: {
          item: { type: "agentMessage", id: "item-1", text: "Hello", phase: null },
          threadId: "t",
          turnId: "turn-1",
          completedAtMs: 1,
        },
      },
    ]);

    expect(chunks).toEqual([
      { type: "text-start", id: "item-1" },
      { type: "text-delta", id: "item-1", delta: "Hello" },
      { type: "text-end", id: "item-1" },
    ]);
  });

  it("maps command execution to a dynamic tool with streamed output", () => {
    const chunks = convertAll([
      {
        method: "item/started",
        params: {
          item: {
            type: "commandExecution",
            id: "cmd-1",
            command: "ls",
            cwd: "/tmp",
            processId: null,
            status: "inProgress",
            aggregatedOutput: null,
            exitCode: null,
          },
          threadId: "t",
          turnId: "turn-1",
          startedAtMs: 0,
        },
      },
      {
        method: "item/commandExecution/outputDelta",
        params: { threadId: "t", turnId: "turn-1", itemId: "cmd-1", delta: "a.txt\n" },
      },
      {
        method: "item/completed",
        params: {
          item: {
            type: "commandExecution",
            id: "cmd-1",
            command: "ls",
            cwd: "/tmp",
            processId: null,
            status: "completed",
            aggregatedOutput: "a.txt\n",
            exitCode: 0,
            durationMs: 5,
          },
          threadId: "t",
          turnId: "turn-1",
          completedAtMs: 1,
        },
      },
    ]);

    expect(chunks).toEqual([
      { type: "tool-input-start", toolCallId: "cmd-1", toolName: "shell", dynamic: true },
      {
        type: "tool-input-available",
        toolCallId: "cmd-1",
        toolName: "shell",
        input: { command: "ls", cwd: "/tmp" },
        dynamic: true,
      },
      {
        type: "tool-output-available",
        toolCallId: "cmd-1",
        output: { aggregatedOutput: "a.txt\n" },
        preliminary: true,
        dynamic: true,
      },
      {
        type: "tool-output-available",
        toolCallId: "cmd-1",
        output: { aggregatedOutput: "a.txt\n", exitCode: 0, status: "completed", durationMs: 5 },
        dynamic: true,
      },
    ]);
  });

  it("maps failed and declined tool items to error and denied chunks", () => {
    const failed = convertAll([
      {
        method: "item/completed",
        params: {
          item: {
            type: "commandExecution",
            id: "cmd-1",
            command: "false",
            cwd: "/",
            processId: null,
            status: "failed",
            aggregatedOutput: "boom",
            exitCode: 1,
          },
          threadId: "t",
          turnId: "turn-1",
          completedAtMs: 1,
        },
      },
    ]);
    expect(failed).toEqual([
      { type: "tool-output-error", toolCallId: "cmd-1", errorText: "boom", dynamic: true },
    ]);

    const declined = convertAll([
      {
        method: "item/completed",
        params: {
          item: {
            type: "fileChange",
            id: "fc-1",
            changes: [],
            status: "declined",
          },
          threadId: "t",
          turnId: "turn-1",
          completedAtMs: 1,
        },
      },
    ]);
    expect(declined).toEqual([{ type: "tool-output-denied", toolCallId: "fc-1" }]);
  });

  it("maps reasoning deltas, including codex summary indices", () => {
    const chunks = convertAll([
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
        params: { threadId: "t", turnId: "turn-1", itemId: "r-1", delta: "think", contentIndex: 0 },
      },
      {
        method: "item/reasoning/summaryTextDelta",
        params: { threadId: "t", turnId: "turn-1", itemId: "r-1", delta: "sum", summaryIndex: 0 },
      },
      {
        method: "item/completed",
        params: {
          item: { type: "reasoning", id: "r-1", summary: ["sum"], content: ["think"] },
          threadId: "t",
          turnId: "turn-1",
          completedAtMs: 1,
        },
      },
    ]);

    expect(chunks).toEqual([
      { type: "reasoning-start", id: "r-1" },
      { type: "reasoning-delta", id: "r-1", delta: "think" },
      { type: "reasoning-start", id: "r-1#summary-0" },
      { type: "reasoning-delta", id: "r-1#summary-0", delta: "sum" },
      { type: "reasoning-end", id: "r-1#summary-0" },
      { type: "reasoning-end", id: "r-1" },
    ]);
  });

  it("closes dangling parts and maps turn status on completion", () => {
    const converter = new UIMessageChunkConverter();
    converter.convert({
      method: "item/started",
      params: {
        item: { type: "agentMessage", id: "item-1", text: "", phase: null },
        threadId: "t",
        turnId: "turn-1",
        startedAtMs: 0,
      },
    });
    const chunks = converter.convert({
      method: "turn/completed",
      params: { threadId: "t", turn: turn("failed") },
    });

    expect(chunks).toEqual([
      { type: "text-end", id: "item-1" },
      { type: "finish-step" },
      { type: "finish", finishReason: "error" },
    ]);
    expect(converter.isFinished).toBe(true);
  });

  it("maps plan updates and errors to data and error chunks", () => {
    const chunks = convertAll([
      {
        method: "turn/plan/updated",
        params: {
          threadId: "t",
          turnId: "turn-1",
          explanation: null,
          plan: [{ step: "look around", status: "inProgress" }],
        },
      },
      { method: "error", params: { error: { message: "harness blew up" } } },
    ]);

    expect(chunks).toEqual([
      {
        type: "data-turnPlan",
        id: "turn-plan:turn-1",
        data: { explanation: null, plan: [{ step: "look around", status: "inProgress" }] },
      },
      { type: "error", errorText: "harness blew up" },
    ]);
  });
});
