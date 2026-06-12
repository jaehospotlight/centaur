import { spawn, type ChildProcess } from "node:child_process";
import { createInterface } from "node:readline";
import type { RequestId, ServerNotification } from "@centaur/harness-events";

export type HarnessName = "codex" | "claude-code" | "amp";

export interface HarnessServerOptions {
  /** Which harness CLI the Rust server should wrap. */
  harness: HarnessName;
  /** Path to the `harness-server` binary. Defaults to $HARNESS_SERVER_BIN or `harness-server` on PATH. */
  serverBin?: string;
  /** Override the full argv passed to the binary (defaults to `[<harness>, "--mode", "jsonrpc"]`). */
  serverArgs?: string[];
  /** Working directory for the server process (and default cwd for threads). */
  cwd?: string;
  /** Extra environment variables (e.g. CLAUDE_BIN, CODEX_BIN, AMP_BIN, CLAUDE_MODEL). */
  env?: Record<string, string | undefined>;
  /** Receives harness-server stderr output line by line. */
  onStderr?: (line: string) => void;
}

export class JsonRpcError extends Error {
  readonly code: number;
  readonly data?: unknown;

  constructor(code: number, message: string, data?: unknown) {
    super(message);
    this.name = "JsonRpcError";
    this.code = code;
    this.data = data;
  }
}

interface Pending {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
}

/**
 * A `harness-server <harness> --mode jsonrpc` child process with a
 * line-delimited JSON-RPC (lite, no `jsonrpc` envelope field) client on its
 * stdio, mirroring how api-rs drives the binary.
 */
export class HarnessServerProcess {
  private readonly child: ChildProcess;
  private readonly pending = new Map<RequestId, Pending>();
  private readonly listeners = new Set<(notification: ServerNotification) => void>();
  private nextId = 1;
  private exitError: Error | null = null;

  /** Resolves when the child process exits. */
  readonly exited: Promise<void>;

  private constructor(child: ChildProcess, onStderr?: (line: string) => void) {
    this.child = child;

    const stdout = child.stdout;
    if (!stdout) throw new Error("harness-server stdout unavailable");
    createInterface({ input: stdout }).on("line", (line) => this.handleLine(line));

    if (child.stderr) {
      const stderr = createInterface({ input: child.stderr });
      stderr.on("line", (line) => onStderr?.(line));
    }

    this.exited = new Promise((resolve) => {
      child.once("exit", (code, signal) => {
        this.exitError = new Error(
          `harness-server exited (code=${code ?? "null"}, signal=${signal ?? "null"})`,
        );
        for (const pending of this.pending.values()) pending.reject(this.exitError);
        this.pending.clear();
        resolve();
      });
    });
  }

  /** Spawn the binary and perform the `initialize` handshake. */
  static async spawn(options: HarnessServerOptions): Promise<HarnessServerProcess> {
    const bin = options.serverBin ?? process.env.HARNESS_SERVER_BIN ?? "harness-server";
    const args = options.serverArgs ?? [options.harness, "--mode", "jsonrpc"];
    const child = spawn(bin, args, {
      cwd: options.cwd,
      env: { ...process.env, ...options.env },
      stdio: ["pipe", "pipe", "pipe"],
    });
    const server = new HarnessServerProcess(child, options.onStderr);
    await server.request("initialize", {
      clientInfo: { name: "@centaur/ai-sdk", title: "Centaur AI SDK adapter", version: "0.1.0" },
      capabilities: null,
    });
    return server;
  }

  request<T = unknown>(method: string, params?: unknown): Promise<T> {
    if (this.exitError) return Promise.reject(this.exitError);
    const id = this.nextId++;
    const payload = params === undefined ? { id, method } : { id, method, params };
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject });
      this.child.stdin?.write(`${JSON.stringify(payload)}\n`, (error) => {
        if (error) {
          this.pending.delete(id);
          reject(error);
        }
      });
    });
  }

  /** Subscribe to server notifications; returns an unsubscribe function. */
  subscribe(listener: (notification: ServerNotification) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  close(): void {
    this.child.kill();
  }

  private handleLine(line: string): void {
    const trimmed = line.trim();
    if (!trimmed) return;
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(trimmed) as Record<string, unknown>;
    } catch {
      return;
    }

    if (typeof message.method === "string" && message.id === undefined) {
      const notification = message as unknown as ServerNotification;
      for (const listener of this.listeners) listener(notification);
      return;
    }

    if (message.id !== undefined) {
      const pending = this.pending.get(message.id as RequestId);
      if (!pending) return;
      this.pending.delete(message.id as RequestId);
      if (message.error !== undefined) {
        const error = message.error as { code?: number; message?: string; data?: unknown };
        pending.reject(
          new JsonRpcError(error.code ?? -32000, error.message ?? "unknown error", error.data),
        );
      } else {
        pending.resolve(message.result);
      }
    }
  }
}
