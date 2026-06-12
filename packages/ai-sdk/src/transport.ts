import type { ChatTransport, UIMessage, UIMessageChunk } from "ai";
import type { UserInput } from "@centaur/harness-events";
import { HarnessSession, type HarnessSessionOptions } from "./session.ts";

export interface HarnessChatTransportOptions extends Omit<HarnessSessionOptions, "resumeThreadId"> {
  /** Map chat ids to existing harness thread ids to resume across restarts. */
  resumeThreadIds?: Record<string, string>;
}

/**
 * AI SDK `ChatTransport` backed by a Centaur harness-server process per chat.
 * Plug it into `new Chat({ transport })` (or `useChat`) to drive Codex,
 * Claude Code, or Amp through the normalized App Server V2 protocol instead
 * of a model-API chat route.
 *
 * Harness threads are stateful: only the latest user message is forwarded on
 * each send, and `regenerate-message` is treated as a fresh submission of
 * that message (harness CLIs have no rollback).
 */
export class HarnessChatTransport<UI_MESSAGE extends UIMessage = UIMessage>
  implements ChatTransport<UI_MESSAGE>
{
  private readonly sessions = new Map<string, Promise<HarnessSession>>();
  private readonly options: HarnessChatTransportOptions;

  constructor(options: HarnessChatTransportOptions) {
    this.options = options;
  }

  async sendMessages(
    options: {
      trigger: "submit-message" | "regenerate-message";
      chatId: string;
      messageId: string | undefined;
      messages: UI_MESSAGE[];
      abortSignal: AbortSignal | undefined;
    } & Record<string, unknown>,
  ): Promise<ReadableStream<UIMessageChunk>> {
    const session = await this.session(options.chatId);
    const input = userInputFromMessages(options.messages);
    return session.runTurn(input, { abortSignal: options.abortSignal });
  }

  async reconnectToStream(): Promise<ReadableStream<UIMessageChunk> | null> {
    return null;
  }

  /** Inject input into the chat's currently running turn (turn/steer). */
  async steer(chatId: string, text: string): Promise<void> {
    const session = await this.sessions.get(chatId);
    if (!session) throw new Error(`no session for chat ${chatId}`);
    await session.steer([{ type: "text", text }]);
  }

  /** The harness thread id backing a chat, once started (useful for resume). */
  async threadId(chatId: string): Promise<string | undefined> {
    const session = await this.sessions.get(chatId);
    return session?.threadId;
  }

  /** Kill all harness-server processes owned by this transport. */
  async close(): Promise<void> {
    const sessions = await Promise.allSettled(this.sessions.values());
    this.sessions.clear();
    for (const session of sessions) {
      if (session.status === "fulfilled") session.value.close();
    }
  }

  private session(chatId: string): Promise<HarnessSession> {
    let session = this.sessions.get(chatId);
    if (!session) {
      const { resumeThreadIds, ...sessionOptions } = this.options;
      session = HarnessSession.start({
        ...sessionOptions,
        resumeThreadId: resumeThreadIds?.[chatId],
      });
      session.catch(() => this.sessions.delete(chatId));
      this.sessions.set(chatId, session);
    }
    return session;
  }
}

/**
 * Convert the latest user UI message into harness `UserInput` blocks. Text
 * parts map directly; file parts map to image/text inputs by media type.
 */
export function userInputFromMessages(messages: readonly UIMessage[]): UserInput[] {
  const lastUserMessage = [...messages].reverse().find((message) => message.role === "user");
  if (!lastUserMessage) return [{ type: "text", text: "continue" }];

  const input: UserInput[] = [];
  for (const part of lastUserMessage.parts) {
    if (part.type === "text") {
      input.push({ type: "text", text: part.text });
    } else if (part.type === "file") {
      if (part.mediaType.startsWith("image/")) {
        input.push({ type: "image", url: part.url });
      } else {
        input.push({ type: "text", text: `[Attached file: ${part.filename ?? part.url}]` });
      }
    }
  }
  if (input.length === 0) input.push({ type: "text", text: "continue" });
  return input;
}
