import { beforeEach, describe, expect, it, vi } from "vitest";

import { BoltSlackApp } from "../src/lib/slack/app";
import type { StreamChunk } from "../src/lib/slack/types";

const slackApiCall = vi.hoisted(() => vi.fn());

vi.mock("@slack/web-api", () => ({
  WebClient: class WebClient {
    apiCall = slackApiCall;

    auth = {
      test: vi.fn(async () => ({ ok: true, user_id: "UBOT" })),
    };

    users = {
      info: vi.fn(),
    };
  },
}));

vi.mock("@slack/bolt", () => ({
  App: class App {
    event = vi.fn();

    processEvent = vi.fn();
  },
  verifySlackRequest: vi.fn(),
}));

function createAdapter() {
  return new BoltSlackApp("xoxb-test", "signing-secret").getSlackAdapter() as unknown as {
    stream(
      threadId: string,
      stream: AsyncIterable<string | StreamChunk>,
      options?: { taskDisplayMode?: "timeline" | "plan" },
    ): Promise<{ id: string }>;
  };
}

function streamCallParams(method: string): Record<string, unknown>[] {
  return slackApiCall.mock.calls
    .filter(([calledMethod]) => calledMethod === method)
    .map(([, params]) => params as Record<string, unknown>);
}

describe("Slack stream payloads", () => {
  beforeEach(() => {
    slackApiCall.mockReset();
    slackApiCall.mockImplementation(async (method: string) => ({
      ok: true,
      ...(method === "chat.startStream" ? { ts: "1700000000.000100" } : {}),
    }));
  });

  it("uses chunk-mode for markdown and structured updates", async () => {
    const adapter = createAdapter();

    await adapter.stream("slack:C123:1700000000.000001", (async function* () {
      yield { type: "markdown_text", text: "\u200b" } satisfies StreamChunk;
      yield { type: "plan_update", title: "Completed" } satisfies StreamChunk;
      yield { type: "markdown_text", text: "pong" } satisfies StreamChunk;
    })(), { taskDisplayMode: "plan" });

    const start = streamCallParams("chat.startStream")[0];
    const appends = streamCallParams("chat.appendStream");

    expect(start).toEqual(expect.objectContaining({
      chunks: [{ type: "markdown_text", text: "\u200b" }],
    }));
    expect(start).not.toHaveProperty("markdown_text");
    expect(appends[0]).toEqual(expect.objectContaining({
      chunks: [{ type: "plan_update", title: "Completed" }],
    }));
    expect(appends[0]).not.toHaveProperty("markdown_text");
    expect(appends[1]).toEqual(expect.objectContaining({
      chunks: [{ type: "markdown_text", text: "pong" }],
    }));
    expect(appends[1]).not.toHaveProperty("markdown_text");
  });

  it("can start directly with a structured chunk", async () => {
    const adapter = createAdapter();

    await adapter.stream("slack:C123:1700000000.000001", (async function* () {
      yield { type: "plan_update", title: "Working" } satisfies StreamChunk;
    })());

    const start = streamCallParams("chat.startStream")[0];
    const appends = streamCallParams("chat.appendStream");

    expect(start).toEqual(expect.objectContaining({
      chunks: [{ type: "plan_update", title: "Working" }],
    }));
    expect(start).not.toHaveProperty("markdown_text");
    expect(appends).toHaveLength(0);
  });
});
