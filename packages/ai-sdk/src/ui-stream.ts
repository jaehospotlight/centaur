import type { UIMessageChunk } from "ai";
import type {
  ServerNotification,
  ThreadItem,
  TurnStatus,
} from "@centaur/harness-events";

/** Data parts emitted alongside the standard AI SDK chunks. */
export interface CentaurUIDataTypes {
  plan: { text: string };
  turnPlan: {
    explanation: string | null;
    plan: Array<{ step: string; status: string }>;
  };
  threadName: { threadName: string };
  contextCompaction: { itemId: string };
  [key: string]: unknown;
}

type OpenPart =
  | { kind: "text" }
  | { kind: "reasoning"; summaryIds: Set<string> }
  | { kind: "plan"; text: string }
  | { kind: "tool"; output: string };

/**
 * Stateful converter from harness-server App Server V2 notifications to AI
 * SDK UI message chunks. One converter handles exactly one turn; the caller
 * is responsible for filtering notifications to a single thread.
 */
export class UIMessageChunkConverter {
  private readonly open = new Map<string, OpenPart>();
  private finished = false;

  get isFinished(): boolean {
    return this.finished;
  }

  convert(notification: ServerNotification): UIMessageChunk[] {
    switch (notification.method) {
      case "turn/started":
        return [{ type: "start", messageId: notification.params.turn.id }, { type: "start-step" }];
      case "turn/completed": {
        const chunks = this.closeOpenParts();
        chunks.push({ type: "finish-step" });
        chunks.push({
          type: "finish",
          finishReason: finishReasonFor(notification.params.turn.status),
        });
        this.finished = true;
        return chunks;
      }
      case "turn/plan/updated":
        return [
          {
            type: "data-turnPlan",
            id: `turn-plan:${notification.params.turnId}`,
            data: {
              explanation: notification.params.explanation,
              plan: notification.params.plan,
            },
          },
        ];
      case "thread/name/updated":
        return [
          {
            type: "data-threadName",
            data: { threadName: notification.params.threadName },
            transient: true,
          },
        ];
      case "error":
        return [{ type: "error", errorText: notification.params.error.message }];
      case "item/started":
        return this.itemStarted(notification.params.item);
      case "item/completed":
        return this.itemCompleted(notification.params.item);
      case "item/agentMessage/delta":
        return this.textDelta(notification.params.itemId, notification.params.delta);
      case "item/reasoning/textDelta":
        return this.reasoningDelta(notification.params.itemId, notification.params.delta);
      case "item/reasoning/summaryTextDelta":
        return this.reasoningSummaryDelta(
          notification.params.itemId,
          notification.params.summaryIndex,
          notification.params.delta,
        );
      case "item/plan/delta":
        return this.planDelta(notification.params.itemId, notification.params.delta);
      case "item/commandExecution/outputDelta":
        return this.toolOutputDelta(notification.params.itemId, notification.params.delta);
      case "item/mcpToolCall/progress":
        return [
          {
            type: "tool-output-available",
            toolCallId: notification.params.itemId,
            output: { progress: notification.params.message },
            preliminary: true,
            dynamic: true,
          },
        ];
      case "item/fileChange/patchUpdated":
        return [
          {
            type: "tool-output-available",
            toolCallId: notification.params.itemId,
            output: { changes: notification.params.changes },
            preliminary: true,
            dynamic: true,
          },
        ];
      default:
        return [];
    }
  }

  private itemStarted(item: ThreadItem): UIMessageChunk[] {
    switch (item.type) {
      case "userMessage":
        return [];
      case "agentMessage":
        this.open.set(item.id, { kind: "text" });
        return [{ type: "text-start", id: item.id }];
      case "reasoning":
        this.open.set(item.id, { kind: "reasoning", summaryIds: new Set() });
        return [{ type: "reasoning-start", id: item.id }];
      case "plan": {
        this.open.set(item.id, { kind: "plan", text: item.text ?? "" });
        return [{ type: "data-plan", id: item.id, data: { text: item.text ?? "" } }];
      }
      case "commandExecution":
        return this.toolInput(item.id, "shell", { command: item.command, cwd: item.cwd });
      case "fileChange":
        return this.toolInput(item.id, "fileChange", { changes: item.changes });
      case "mcpToolCall":
        return this.toolInput(item.id, `${item.server}.${item.tool}`, item.arguments);
      case "dynamicToolCall":
        return this.toolInput(item.id, item.tool, item.arguments);
      case "webSearch":
        return this.toolInput(item.id, "webSearch", { query: item.query });
      case "contextCompaction":
        return [
          { type: "data-contextCompaction", data: { itemId: item.id }, transient: true },
        ];
      default:
        return this.toolInput(item.id, item.type, item);
    }
  }

  private itemCompleted(item: ThreadItem): UIMessageChunk[] {
    const open = this.open.get(item.id);
    this.open.delete(item.id);
    switch (item.type) {
      case "userMessage":
        return [];
      case "agentMessage": {
        // Some harnesses (e.g. Amp before chunking kicks in) can deliver the
        // full text only at completion; backfill a part if none was streamed.
        if (!open) {
          return [
            { type: "text-start", id: item.id },
            { type: "text-delta", id: item.id, delta: item.text },
            { type: "text-end", id: item.id },
          ];
        }
        return [{ type: "text-end", id: item.id }];
      }
      case "reasoning": {
        const chunks: UIMessageChunk[] = [];
        if (open?.kind === "reasoning") {
          for (const summaryId of open.summaryIds) {
            chunks.push({ type: "reasoning-end", id: summaryId });
          }
        }
        chunks.push({ type: "reasoning-end", id: item.id });
        return chunks;
      }
      case "plan":
        return [{ type: "data-plan", id: item.id, data: { text: item.text } }];
      case "commandExecution": {
        if (item.status === "declined") {
          return [{ type: "tool-output-denied", toolCallId: item.id }];
        }
        if (item.status === "failed") {
          return [
            {
              type: "tool-output-error",
              toolCallId: item.id,
              errorText: item.aggregatedOutput || `command failed (exit ${item.exitCode})`,
              dynamic: true,
            },
          ];
        }
        return [
          {
            type: "tool-output-available",
            toolCallId: item.id,
            output: {
              aggregatedOutput: item.aggregatedOutput,
              exitCode: item.exitCode,
              status: item.status,
              durationMs: item.durationMs ?? null,
            },
            dynamic: true,
          },
        ];
      }
      case "fileChange": {
        if (item.status === "declined") {
          return [{ type: "tool-output-denied", toolCallId: item.id }];
        }
        if (item.status === "failed") {
          return [
            {
              type: "tool-output-error",
              toolCallId: item.id,
              errorText: "file change failed",
              dynamic: true,
            },
          ];
        }
        return [
          {
            type: "tool-output-available",
            toolCallId: item.id,
            output: { changes: item.changes, status: item.status },
            dynamic: true,
          },
        ];
      }
      case "mcpToolCall": {
        if (item.error) {
          return [
            {
              type: "tool-output-error",
              toolCallId: item.id,
              errorText: item.error.message,
              dynamic: true,
            },
          ];
        }
        return [
          { type: "tool-output-available", toolCallId: item.id, output: item.result, dynamic: true },
        ];
      }
      case "dynamicToolCall": {
        if (item.success === false) {
          return [
            {
              type: "tool-output-error",
              toolCallId: item.id,
              errorText: toolErrorText(item.contentItems),
              dynamic: true,
            },
          ];
        }
        return [
          {
            type: "tool-output-available",
            toolCallId: item.id,
            output: item.contentItems,
            dynamic: true,
          },
        ];
      }
      case "webSearch":
        return [
          {
            type: "tool-output-available",
            toolCallId: item.id,
            output: { action: item.action },
            dynamic: true,
          },
        ];
      case "contextCompaction":
        return [];
      default:
        return [
          { type: "tool-output-available", toolCallId: item.id, output: item, dynamic: true },
        ];
    }
  }

  private toolInput(toolCallId: string, toolName: string, input: unknown): UIMessageChunk[] {
    this.open.set(toolCallId, { kind: "tool", output: "" });
    return [
      { type: "tool-input-start", toolCallId, toolName, dynamic: true },
      { type: "tool-input-available", toolCallId, toolName, input, dynamic: true },
    ];
  }

  private textDelta(itemId: string, delta: string): UIMessageChunk[] {
    if (this.open.get(itemId)?.kind === "text") {
      return [{ type: "text-delta", id: itemId, delta }];
    }
    this.open.set(itemId, { kind: "text" });
    return [
      { type: "text-start", id: itemId },
      { type: "text-delta", id: itemId, delta },
    ];
  }

  private reasoningDelta(itemId: string, delta: string): UIMessageChunk[] {
    if (this.open.get(itemId)?.kind === "reasoning") {
      return [{ type: "reasoning-delta", id: itemId, delta }];
    }
    this.open.set(itemId, { kind: "reasoning", summaryIds: new Set() });
    return [
      { type: "reasoning-start", id: itemId },
      { type: "reasoning-delta", id: itemId, delta },
    ];
  }

  private reasoningSummaryDelta(
    itemId: string,
    summaryIndex: number,
    delta: string,
  ): UIMessageChunk[] {
    let open = this.open.get(itemId);
    const chunks: UIMessageChunk[] = [];
    if (open?.kind !== "reasoning") {
      open = { kind: "reasoning", summaryIds: new Set() };
      this.open.set(itemId, open);
      chunks.push({ type: "reasoning-start", id: itemId });
    }
    const summaryId = `${itemId}#summary-${summaryIndex}`;
    if (!open.summaryIds.has(summaryId)) {
      open.summaryIds.add(summaryId);
      chunks.push({ type: "reasoning-start", id: summaryId });
    }
    chunks.push({ type: "reasoning-delta", id: summaryId, delta });
    return chunks;
  }

  private planDelta(itemId: string, delta: string): UIMessageChunk[] {
    const open = this.open.get(itemId);
    const text = (open?.kind === "plan" ? open.text : "") + delta;
    this.open.set(itemId, { kind: "plan", text });
    return [{ type: "data-plan", id: itemId, data: { text } }];
  }

  private toolOutputDelta(itemId: string, delta: string): UIMessageChunk[] {
    const open = this.open.get(itemId);
    const output = (open?.kind === "tool" ? open.output : "") + delta;
    this.open.set(itemId, { kind: "tool", output });
    return [
      {
        type: "tool-output-available",
        toolCallId: itemId,
        output: { aggregatedOutput: output },
        preliminary: true,
        dynamic: true,
      },
    ];
  }

  private closeOpenParts(): UIMessageChunk[] {
    const chunks: UIMessageChunk[] = [];
    for (const [id, part] of this.open) {
      if (part.kind === "text") {
        chunks.push({ type: "text-end", id });
      } else if (part.kind === "reasoning") {
        for (const summaryId of part.summaryIds) {
          chunks.push({ type: "reasoning-end", id: summaryId });
        }
        chunks.push({ type: "reasoning-end", id });
      }
    }
    this.open.clear();
    return chunks;
  }
}

function finishReasonFor(status: TurnStatus): "stop" | "error" | "other" {
  switch (status) {
    case "completed":
      return "stop";
    case "failed":
      return "error";
    default:
      return "other";
  }
}

function toolErrorText(contentItems: unknown): string {
  if (Array.isArray(contentItems)) {
    const texts = contentItems
      .map((item) =>
        item && typeof item === "object" && "text" in item ? String(item.text) : null,
      )
      .filter((text): text is string => text !== null);
    if (texts.length > 0) return texts.join("\n");
  }
  return "tool call failed";
}
