export type TextBlock = { type: "text"; text: string };
export type ToolUseBlock = {
  type: "tool_use";
  id: string;
  name: string;
  input: Record<string, unknown>;
};
export type ToolResultBlock = {
  type: "tool_result";
  tool_use_id: string;
  content: string | ContentBlock[];
};
export type ThinkingBlock = { type: "thinking"; thinking: string };

export type ContentBlock =
  | TextBlock
  | ToolUseBlock
  | ToolResultBlock
  | ThinkingBlock;

export type AssistantEvent = {
  type: "assistant";
  message: { role: "assistant"; content: ContentBlock[] };
};

export type ToolEvent = {
  type: "tool";
  content: ToolResultBlock[];
};

export type SystemEvent = {
  type: "system";
  subtype: "init";
  session_id: string;
};

export type ErrorEvent = {
  type: "error";
  error: string;
  message?: string;
};

export type RawEvent = {
  type: "raw";
  text: string;
};

export type ResultEvent = {
  type: "result";
  result: string;
};

export type ThreadStartedEvent = {
  type: "thread.started";
  thread_id: string;
};

export type ItemCompletedEvent = {
  type: "item.completed";
  item: { type: string; text: string };
};

export type FileChangeEvent = {
  type: "file_change";
  changes: Array<{ path: string; kind: "add" | "delete" | "update" }>;
};

export type CommandExecutionEvent = {
  type: "command_execution";
  command: string;
  aggregated_output?: string;
  exit_code?: number;
  status?: string;
};

export type ReasoningEvent = {
  type: "reasoning";
  text: string;
};

export type ThreadEvent =
  | AssistantEvent
  | ToolEvent
  | SystemEvent
  | ErrorEvent
  | RawEvent
  | ResultEvent
  | ThreadStartedEvent
  | ItemCompletedEvent
  | FileChangeEvent
  | CommandExecutionEvent
  | ReasoningEvent;

export type Harness = "amp" | "claude-code" | "codex" | "pi-mono" | "engineer";
export type ThreadState = "running" | "idle" | "stopped" | "working" | "waiting" | "error";

export type Turn = {
  turn_id: number;
  user_message: string;
  events: ThreadEvent[];
  result: string;
  started_at: number;
  finished_at: number | null;
  exit_code: number | null;
  timed_out: boolean;
  duration_s: number;
};

export type ThreadDetail = {
  slack_thread_key: string;
  container_id: string;
  harness: Harness;
  agent_thread_id: string | null;
  state: ThreadState;
  created_at: number;
  last_activity: number;
  turns: Turn[];
  thread_name?: string | null;
};

export type ThreadSummary = {
  slack_thread_key: string;
  container_id: string;
  harness: string;
  agent_thread_id: string | null;
  state: string;
  created_at: number;
  last_activity: number;
  turn_count: number;
  last_result: string;
  first_message?: string;
  thread_name?: string | null;
};

export const PHASES = [
  "research",
  "plan",
  "clarify",
  "implement",
  "review",
  "publish",
] as const;

export type Phase = (typeof PHASES)[number];
