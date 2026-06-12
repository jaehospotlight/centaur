import {
  stepCountIs,
  streamText,
  type LanguageModel,
  type ModelMessage,
  type ToolSet,
} from "ai";

/**
 * One emitted stdout line. The bridge speaks the Claude-CLI stream-json
 * dialect that `crates/harness-server` already normalizes (see
 * `AnthropicStreamEvent` in anthropic.rs), so the Rust side treats an AI SDK
 * agent exactly like any other harness producer.
 */
export type EmitLine = (line: Record<string, unknown>) => void;

export interface BridgeOptions {
  model: LanguageModel;
  tools: ToolSet;
  sessionId: string;
  emit: EmitLine;
  system?: string;
  /** Safety bound on agent-loop steps per user turn. */
  maxStepsPerTurn?: number;
}

interface IncomingUserLine {
  type?: string;
  message?: { content?: Array<{ type?: string; text?: string }> };
}

export class AiSdkBridge {
  private readonly options: BridgeOptions;
  private readonly messages: ModelMessage[] = [];
  private readonly pending: ModelMessage[] = [];
  private running = false;
  private messageCounter = 0;

  constructor(options: BridgeOptions) {
    this.options = options;
  }

  /** Feed one raw stdin line (a `{"type":"user",...}` message from harness-server). */
  handleStdinLine(line: string): void {
    const trimmed = line.trim();
    if (!trimmed) return;
    let parsed: IncomingUserLine;
    try {
      parsed = JSON.parse(trimmed) as IncomingUserLine;
    } catch {
      return;
    }
    if (parsed.type !== "user") return;
    const text = (parsed.message?.content ?? [])
      .filter((block) => block.type === "text" && typeof block.text === "string")
      .map((block) => block.text as string);
    if (text.length === 0) return;
    this.pending.push({
      role: "user",
      content: text.map((value) => ({ type: "text" as const, text: value })),
    });
    if (!this.running) void this.run();
  }

  /** Resolves once the current turn (if any) has fully drained. */
  async idle(): Promise<void> {
    while (this.running) {
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
  }

  private async run(): Promise<void> {
    this.running = true;
    try {
      while (this.pending.length > 0) {
        this.messages.push(...this.pending.splice(0));
        await this.runTurn();
        this.options.emit({ type: "result", subtype: "success" });
      }
    } catch (error) {
      this.options.emit({
        type: "result",
        subtype: "error_during_execution",
        is_error: true,
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      this.running = false;
    }
  }

  private async runTurn(): Promise<void> {
    const maxSteps = this.options.maxStepsPerTurn ?? 24;
    for (let step = 0; step < maxSteps; step++) {
      const finishReason = await this.runStep();
      // Steered input arrives on stdin mid-turn; drain it between steps so
      // the model sees it before deciding it is done.
      const steered = this.pending.splice(0);
      this.messages.push(...steered);
      if (finishReason !== "tool-calls" && steered.length === 0) return;
    }
    throw new Error(`turn exceeded ${maxSteps} steps`);
  }

  private async runStep(): Promise<string> {
    const { emit } = this.options;
    const messageId = `msg_${++this.messageCounter}`;
    emit({
      type: "stream_event",
      event: { type: "message_start", message: { id: messageId, content: [] } },
    });

    const result = streamText({
      model: this.options.model,
      system: this.options.system,
      messages: this.messages,
      tools: this.options.tools,
      // One model call per step: the bridge owns the agent loop so steered
      // user input can be injected between steps (see runTurn).
      stopWhen: stepCountIs(1),
    });

    const blockIndexById = new Map<string, number>();
    const textById = new Map<string, string>();
    const reasoningById = new Map<string, string>();
    const toolCalls: Array<{ id: string; name: string; input: unknown }> = [];
    const toolResultLines: Array<Record<string, unknown>> = [];
    let nextBlockIndex = 0;
    let finishReason = "stop";

    const startBlock = (id: string, contentBlock: Record<string, unknown>): number => {
      const index = nextBlockIndex++;
      blockIndexById.set(id, index);
      emit({
        type: "stream_event",
        event: { type: "content_block_start", index, content_block: contentBlock },
      });
      return index;
    };
    const stopBlock = (id: string): void => {
      const index = blockIndexById.get(id);
      if (index === undefined) return;
      emit({ type: "stream_event", event: { type: "content_block_stop", index } });
    };

    for await (const part of result.fullStream) {
      switch (part.type) {
        case "text-start":
          startBlock(part.id, { type: "text", text: "" });
          textById.set(part.id, "");
          break;
        case "text-delta":
          textById.set(part.id, (textById.get(part.id) ?? "") + part.text);
          emit({
            type: "stream_event",
            event: {
              type: "content_block_delta",
              index: blockIndexById.get(part.id) ?? 0,
              delta: { type: "text_delta", text: part.text },
            },
          });
          break;
        case "text-end":
          stopBlock(part.id);
          break;
        case "reasoning-start":
          startBlock(part.id, { type: "thinking", thinking: "" });
          reasoningById.set(part.id, "");
          break;
        case "reasoning-delta":
          reasoningById.set(part.id, (reasoningById.get(part.id) ?? "") + part.text);
          emit({
            type: "stream_event",
            event: {
              type: "content_block_delta",
              index: blockIndexById.get(part.id) ?? 0,
              delta: { type: "thinking_delta", thinking: part.text },
            },
          });
          break;
        case "reasoning-end":
          stopBlock(part.id);
          break;
        case "tool-call":
          toolCalls.push({ id: part.toolCallId, name: part.toolName, input: part.input });
          break;
        case "tool-result":
          toolResultLines.push(toolResultLine(part.toolCallId, part.output, false));
          break;
        case "tool-error":
          toolResultLines.push(
            toolResultLine(
              part.toolCallId,
              part.error instanceof Error ? part.error.message : String(part.error),
              true,
            ),
          );
          break;
        case "finish":
          finishReason = part.finishReason;
          break;
        case "error":
          throw part.error instanceof Error ? part.error : new Error(String(part.error));
        default:
          break;
      }
    }

    const content: Array<Record<string, unknown>> = [];
    for (const [id, thinking] of reasoningById) {
      void id;
      content.push({ type: "thinking", thinking });
    }
    for (const [id, text] of textById) {
      void id;
      content.push({ type: "text", text });
    }
    for (const call of toolCalls) {
      content.push({ type: "tool_use", id: call.id, name: call.name, input: call.input });
    }
    emit({
      type: "assistant",
      is_partial: false,
      message: {
        id: messageId,
        stop_reason: finishReason === "tool-calls" ? "tool_use" : "end_turn",
        content,
      },
    });
    for (const line of toolResultLines) emit(line);

    const response = await result.response;
    this.messages.push(...response.messages);
    return finishReason;
  }
}

interface CommandOutput {
  stdout: string;
  stderr: string;
  exitCode: number;
}

function isCommandOutput(output: unknown): output is CommandOutput {
  return (
    typeof output === "object" &&
    output !== null &&
    "exitCode" in output &&
    ("stdout" in output || "stderr" in output)
  );
}

function toolResultLine(
  toolUseId: string,
  output: unknown,
  isError: boolean,
): Record<string, unknown> {
  if (isCommandOutput(output)) {
    return {
      type: "user",
      message: {
        role: "user",
        content: [
          {
            type: "tool_result",
            tool_use_id: toolUseId,
            content: `${output.stdout}${output.stderr}`,
            is_error: isError || output.exitCode !== 0,
          },
        ],
      },
      tool_use_result: {
        stdout: output.stdout,
        stderr: output.stderr,
        exit_code: output.exitCode,
      },
    };
  }
  return {
    type: "user",
    message: {
      role: "user",
      content: [
        {
          type: "tool_result",
          tool_use_id: toolUseId,
          content: typeof output === "string" ? output : JSON.stringify(output),
          is_error: isError,
        },
      ],
    },
  };
}
