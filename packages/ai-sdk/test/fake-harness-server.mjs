// Minimal stand-in for `harness-server <harness> --mode jsonrpc`: speaks the
// same line-delimited JSON-RPC lite protocol and streams a canned turn that
// echoes the user's text, so transport tests run without any harness CLI.
import { createInterface } from "node:readline";

const write = (value) => process.stdout.write(`${JSON.stringify(value)}\n`);

const turn = (status) => ({
  id: "turn-1",
  items: [],
  itemsView: "full",
  status,
  error: null,
  startedAt: null,
  completedAt: null,
  durationMs: null,
});

createInterface({ input: process.stdin }).on("line", (line) => {
  if (!line.trim()) return;
  const request = JSON.parse(line);
  switch (request.method) {
    case "initialize":
      write({
        id: request.id,
        result: {
          userAgent: "fake-harness-server",
          codexHome: "/tmp",
          platformFamily: "unix",
          platformOs: "fake",
        },
      });
      break;
    case "thread/start":
      write({ id: request.id, result: { thread: { id: "thread-1" } } });
      break;
    case "turn/start": {
      write({ id: request.id, result: { turn: turn("inProgress") } });
      const text = request.params.input
        .filter((input) => input.type === "text")
        .map((input) => input.text)
        .join(" ");
      write({ method: "thread/started", params: { thread: { id: "thread-1" } } });
      write({ method: "turn/started", params: { threadId: "thread-1", turn: turn("inProgress") } });
      write({
        method: "item/started",
        params: {
          item: { type: "agentMessage", id: "msg-1", text: "", phase: null },
          threadId: "thread-1",
          turnId: "turn-1",
          startedAtMs: 0,
        },
      });
      for (const delta of [`echo: `, text]) {
        write({
          method: "item/agentMessage/delta",
          params: { threadId: "thread-1", turnId: "turn-1", itemId: "msg-1", delta },
        });
      }
      write({
        method: "item/completed",
        params: {
          item: { type: "agentMessage", id: "msg-1", text: `echo: ${text}`, phase: "final_answer" },
          threadId: "thread-1",
          turnId: "turn-1",
          completedAtMs: 1,
        },
      });
      write({ method: "turn/completed", params: { threadId: "thread-1", turn: turn("completed") } });
      break;
    }
    case "turn/interrupt":
      write({ id: request.id, result: {} });
      break;
    default:
      write({
        id: request.id,
        error: { code: -32601, message: `method not found: ${request.method}` },
      });
  }
});
