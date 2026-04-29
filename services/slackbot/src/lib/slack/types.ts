export type TaskStatus = "pending" | "in_progress" | "complete" | "error";

export type SlackBlock = {
  type: string;
  [key: string]: unknown;
};

export type StreamChunk =
  | { type: "markdown_text"; text: string }
  | {
      type: "task_update";
      id: string;
      title: string;
      status: TaskStatus;
      details?: string;
      output?: string;
      sources?: Array<{ type: string; text?: string; url?: string }>;
    }
  | { type: "plan_update"; title: string }
  | { type: "blocks"; blocks: SlackBlock[] };
