import type { UIMessageChunk } from "ai";
import type {
  ThreadStartResponse,
  TurnStartResponse,
  UserInput,
} from "@centaur/harness-events";
import { HarnessServerProcess, type HarnessServerOptions } from "./jsonrpc.ts";
import { UIMessageChunkConverter } from "./ui-stream.ts";

export interface HarnessSessionOptions extends HarnessServerOptions {
  /** Working directory the harness CLI runs in. Defaults to the server process cwd. */
  threadCwd?: string;
  /** Model override passed to `thread/start` (falls through to the harness config when omitted). */
  model?: string;
  /** Resume an existing harness thread instead of starting a fresh one. */
  resumeThreadId?: string;
}

/**
 * One harness-server process owning one thread. Turns run sequentially; the
 * Rust server is single-threaded per process, which matches AI SDK chat
 * semantics (one in-flight response per chat).
 */
export class HarnessSession {
  private activeTurnId: string | null = null;
  readonly server: HarnessServerProcess;
  readonly threadId: string;

  private constructor(server: HarnessServerProcess, threadId: string) {
    this.server = server;
    this.threadId = threadId;
  }

  static async start(options: HarnessSessionOptions): Promise<HarnessSession> {
    const server = await HarnessServerProcess.spawn(options);
    try {
      const threadParams: Record<string, unknown> = {};
      if (options.threadCwd) threadParams.cwd = options.threadCwd;
      if (options.model) threadParams.model = options.model;
      if (options.resumeThreadId) {
        const response = await server.request<{ thread: { id: string } }>("thread/resume", {
          ...threadParams,
          threadId: options.resumeThreadId,
        });
        return new HarnessSession(server, response.thread.id);
      }
      const response = await server.request<ThreadStartResponse>("thread/start", threadParams);
      return new HarnessSession(server, response.thread.id);
    } catch (error) {
      server.close();
      throw error;
    }
  }

  /**
   * Start a turn and stream it back as AI SDK UI message chunks. The stream
   * closes after `turn/completed` (the Rust server always emits one, even on
   * harness failure).
   */
  runTurn(input: UserInput[], options?: { abortSignal?: AbortSignal }): ReadableStream<UIMessageChunk> {
    const converter = new UIMessageChunkConverter();
    let unsubscribe: (() => void) | undefined;
    let removeAbortListener: (() => void) | undefined;
    let exitWatcherActive = true;

    const cleanup = () => {
      exitWatcherActive = false;
      unsubscribe?.();
      removeAbortListener?.();
    };

    return new ReadableStream<UIMessageChunk>({
      start: (controller) => {
        unsubscribe = this.server.subscribe((notification) => {
          const params = notification.params as { threadId?: string; turn?: { id: string } };
          if (params?.threadId && params.threadId !== this.threadId) return;
          if (notification.method === "turn/started") {
            this.activeTurnId = notification.params.turn.id;
          }
          for (const chunk of converter.convert(notification)) {
            controller.enqueue(chunk);
          }
          if (converter.isFinished) {
            this.activeTurnId = null;
            cleanup();
            controller.close();
          }
        });

        const abortSignal = options?.abortSignal;
        if (abortSignal) {
          const onAbort = () => {
            void this.interrupt().catch(() => {});
          };
          if (abortSignal.aborted) onAbort();
          else abortSignal.addEventListener("abort", onAbort, { once: true });
          removeAbortListener = () => abortSignal.removeEventListener("abort", onAbort);
        }

        void this.server.exited.then(() => {
          if (!exitWatcherActive) return;
          cleanup();
          controller.enqueue({ type: "error", errorText: "harness-server exited unexpectedly" });
          controller.close();
        });

        this.server
          .request<TurnStartResponse>("turn/start", { threadId: this.threadId, input })
          .catch((error: unknown) => {
            cleanup();
            controller.enqueue({
              type: "error",
              errorText: error instanceof Error ? error.message : String(error),
            });
            controller.close();
          });
      },
      cancel: () => {
        cleanup();
        void this.interrupt().catch(() => {});
      },
    });
  }

  /** Inject additional user input into the currently running turn. */
  async steer(input: UserInput[]): Promise<void> {
    if (!this.activeTurnId) throw new Error("no active turn to steer");
    await this.server.request("turn/steer", {
      threadId: this.threadId,
      expectedTurnId: this.activeTurnId,
      input,
    });
  }

  async interrupt(): Promise<void> {
    if (!this.activeTurnId) return;
    await this.server.request("turn/interrupt", {
      threadId: this.threadId,
      turnId: this.activeTurnId,
    });
  }

  close(): void {
    this.server.close();
  }
}
