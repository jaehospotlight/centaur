# @centaur/ai-sdk

Vercel AI SDK adapter for Centaur's Rust harness layer. It exposes
`crates/harness-server` — which normalizes the Codex, Claude Code, and Amp
CLIs behind Codex App Server V2 JSON-RPC — as an AI SDK
[`ChatTransport`](https://ai-sdk.dev/docs/ai-sdk-ui/transport), so any
`useChat` / `Chat` application can drive a full agent harness (sessions,
tools, file edits, plans, steering) instead of a raw model endpoint.

```
useChat / Chat ──ChatTransport──▶ @centaur/ai-sdk ──JSON-RPC (stdio)──▶ harness-server ──▶ codex | claude | amp
```

Where Vercel's experimental `HarnessAgent` runs harness CLIs behind the AI
SDK directly, this package runs them behind Centaur's Rust normalizer — the
turn lifecycle, stdout hygiene, session continuity, and per-harness quirks
stay in one place, and every harness behind the protocol gets AI SDK support
for free.

## Usage

### With `useChat` (or any `AbstractChat` subclass)

```tsx
import { useChat } from "@ai-sdk/react";
import { HarnessChatTransport } from "@centaur/ai-sdk";

const transport = new HarnessChatTransport({
  harness: "claude-code", // or "codex" | "amp"
  threadCwd: "/path/to/workspace",
});

// In an Electron main process, SSR app, or anywhere Node can spawn processes:
const { messages, sendMessage } = useChat({ transport });
```

### In-process streaming (Node, scripts, tests)

```ts
import { readUIMessageStream } from "ai";

const stream = await transport.sendMessages({
  trigger: "submit-message",
  chatId: "chat-1",
  messageId: undefined,
  messages: [{ id: "u-1", role: "user", parts: [{ type: "text", text: "What does this repo do?" }] }],
  abortSignal: undefined,
});
for await (const message of readUIMessageStream({ stream })) {
  // each iteration is the assistant UIMessage as it grows
}
```

One `harness-server` process is spawned per chat id; the harness thread is
reused across sends, so multi-turn conversation state lives in the harness
session (the transport only forwards the latest user message).

### HTTP route for a browser `useChat`

The transport returns a standard `ReadableStream<UIMessageChunk>`, so a
server route is one call:

```ts
import { createUIMessageStreamResponse } from "ai";

export async function POST(request: Request) {
  const { id, messages, trigger, messageId } = await request.json();
  const stream = await transport.sendMessages({
    chatId: id,
    messages,
    trigger,
    messageId,
    abortSignal: request.signal,
  });
  return createUIMessageStreamResponse({ stream });
}
```

### Steering a running turn

`turn/steer` is exposed beyond the `ChatTransport` interface:

```ts
await transport.steer(chatId, "also check the tests directory");
```

### Lower-level building blocks

- `HarnessSession` — one server process + one thread; `runTurn(input)` returns
  a `ReadableStream<UIMessageChunk>`, plus `steer` / `interrupt` / resume via
  `resumeThreadId`.
- `HarnessServerProcess` — the raw line-delimited JSON-RPC client.
- `UIMessageChunkConverter` — the pure App-Server-notification →
  `UIMessageChunk` mapping, reusable against any other source of
  `@centaur/harness-events` notifications (e.g. the api-rs SSE stream).

## Event mapping

| harness-server notification | AI SDK chunk |
| --- | --- |
| `turn/started` / `turn/completed` | `start` / `finish` (status → `finishReason`) |
| `item/agentMessage/*` | `text-start` / `text-delta` / `text-end` |
| `item/reasoning/*` (content + summaries) | `reasoning-*` |
| `commandExecution`, `fileChange`, `mcpToolCall`, `dynamicToolCall`, `webSearch` items | dynamic tool chunks (`tool-input-*`, `tool-output-*`; declined → `tool-output-denied`) |
| `item/commandExecution/outputDelta` | preliminary `tool-output-available` (streaming output) |
| `turn/plan/updated`, `plan` items | `data-turnPlan` / `data-plan` parts |
| `thread/name/updated`, `contextCompaction` | transient data parts |
| `error` | `error` |

## Configuration

The `harness-server` binary is resolved from `serverBin`, then
`$HARNESS_SERVER_BIN`, then PATH. Harness CLIs are configured through the
binary's own environment (`CLAUDE_BIN`, `CLAUDE_MODEL`, `CODEX_BIN`,
`AMP_BIN`, `AMP_MODE`, ...), passed via the `env` option.

## Example

```sh
cargo build -p harness-server
HARNESS_SERVER_BIN=../../target/debug/harness-server \
  node examples/chat.ts claude-code "what files are in this directory?"
```

## Tests

`pnpm test` — covers the notification→chunk converter, the transport against
a scripted fake harness-server (no harness CLIs needed), and end-to-end
assembly through the AI SDK's own `readUIMessageStream` state machine.
