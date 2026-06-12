import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { UIMessage, UIMessageChunk } from "ai";
import { HarnessChatTransport, userInputFromMessages } from "./transport.ts";

const fakeServerPath = fileURLToPath(new URL("../test/fake-harness-server.mjs", import.meta.url));

function transport() {
  return new HarnessChatTransport({
    harness: "claude-code",
    serverBin: process.execPath,
    serverArgs: [fakeServerPath],
  });
}

function userMessage(text: string): UIMessage {
  return { id: "u-1", role: "user", parts: [{ type: "text", text }] };
}

async function collect(stream: ReadableStream<UIMessageChunk>): Promise<UIMessageChunk[]> {
  const chunks: UIMessageChunk[] = [];
  for await (const chunk of stream as unknown as AsyncIterable<UIMessageChunk>) {
    chunks.push(chunk);
  }
  return chunks;
}

describe("HarnessChatTransport", () => {
  it("streams a full turn as UI message chunks", async () => {
    const chat = transport();
    try {
      const stream = await chat.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messageId: undefined,
        messages: [userMessage("hello world")],
        abortSignal: undefined,
      });
      const chunks = await collect(stream);

      expect(chunks).toEqual([
        { type: "start", messageId: "turn-1" },
        { type: "start-step" },
        { type: "text-start", id: "msg-1" },
        { type: "text-delta", id: "msg-1", delta: "echo: " },
        { type: "text-delta", id: "msg-1", delta: "hello world" },
        { type: "text-end", id: "msg-1" },
        { type: "finish-step" },
        { type: "finish", finishReason: "stop" },
      ]);
      await expect(chat.threadId("chat-1")).resolves.toBe("thread-1");
    } finally {
      await chat.close();
    }
  });

  it("reuses one session per chat id", async () => {
    const chat = transport();
    try {
      const first = await chat.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messageId: undefined,
        messages: [userMessage("one")],
        abortSignal: undefined,
      });
      await collect(first);
      const second = await chat.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messageId: undefined,
        messages: [userMessage("one"), userMessage("two")],
        abortSignal: undefined,
      });
      const chunks = await collect(second);
      const text = chunks
        .filter((chunk) => chunk.type === "text-delta")
        .map((chunk) => chunk.delta)
        .join("");
      expect(text).toBe("echo: two");
    } finally {
      await chat.close();
    }
  });

  it("surfaces server death as an error chunk instead of hanging", async () => {
    const chat = new HarnessChatTransport({
      harness: "claude-code",
      serverBin: process.execPath,
      // Handles initialize/thread/start, then exits before answering turn/start.
      serverArgs: [
        "-e",
        `
        const { createInterface } = require("node:readline");
        createInterface({ input: process.stdin }).on("line", (line) => {
          const request = JSON.parse(line);
          if (request.method === "turn/start") process.exit(1);
          process.stdout.write(JSON.stringify({ id: request.id, result: { thread: { id: "t" } } }) + "\\n");
        });
        `,
      ],
    });
    try {
      const stream = await chat.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messageId: undefined,
        messages: [userMessage("boom")],
        abortSignal: undefined,
      });
      const chunks = await collect(stream);
      expect(chunks).toHaveLength(1);
      expect(chunks[0]).toMatchObject({ type: "error" });
    } finally {
      await chat.close();
    }
  });
});

describe("userInputFromMessages", () => {
  it("converts the latest user message parts", () => {
    const input = userInputFromMessages([
      userMessage("first"),
      { id: "a-1", role: "assistant", parts: [{ type: "text", text: "reply" }] },
      {
        id: "u-2",
        role: "user",
        parts: [
          { type: "text", text: "look at this" },
          { type: "file", mediaType: "image/png", url: "https://example.com/x.png" },
          { type: "file", mediaType: "application/pdf", url: "https://example.com/doc.pdf" },
        ],
      },
    ]);

    expect(input).toEqual([
      { type: "text", text: "look at this" },
      { type: "image", url: "https://example.com/x.png" },
      { type: "text", text: "[Attached file: https://example.com/doc.pdf]" },
    ]);
  });

  it("falls back to continue when there is no user input", () => {
    expect(userInputFromMessages([])).toEqual([{ type: "text", text: "continue" }]);
  });
});
