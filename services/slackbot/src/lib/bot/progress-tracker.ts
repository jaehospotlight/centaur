import type { CanonicalEvent } from "@centaur/harness-events";
import type { StreamChunk } from "chat";

type ActiveTool = { name: string; input: Record<string, unknown>; startedAt: number };
type StepStatus = "pending" | "in_progress" | "complete" | "error";
type HistoryEntry = { toolId: string; title: string; status: StepStatus };

const MAX_VISIBLE_STEPS = 5;

export class ProgressTracker {
  lastAssistantText = "";
  resultText = "";
  agentThreadId = "";
  initCompleted = false;
  private activeTools = new Map<string, ActiveTool>();
  private stepHistory: HistoryEntry[] = [];

  *update(event: CanonicalEvent): Generator<StreamChunk> {
    if (!this.initCompleted) {
      this.initCompleted = true;
      yield { type: "task_update", id: "init", title: "Started", status: "complete" };
    }

    if (event.type === "assistant" && event.message?.content) {
      let textInThisEvent = "";
      for (const block of event.message.content) {
        if (block.type === "tool_use") {
          this.lastAssistantText = "";
          this.activeTools.set(block.id, { name: block.name, input: block.input, startedAt: Date.now() });
          yield* this.addStep(block.id, friendlyToolLabel(block.name, block.input), "in_progress");
        } else if (block.type === "text" && block.text) {
          textInThisEvent = block.text;
        }
      }
      if (textInThisEvent && this.activeTools.size === 0) {
        this.lastAssistantText = textInThisEvent;
      }
      return;
    }

    if (event.type === "tool" && event.content) {
      for (const block of event.content) {
        const active = this.activeTools.get(block.tool_use_id);
        if (active) {
          this.activeTools.delete(block.tool_use_id);
          yield* this.updateStep(
            block.tool_use_id,
            friendlyToolLabel(active.name, active.input, !block.is_error),
            block.is_error ? "error" : "complete",
          );
        }
      }
      return;
    }

    if (event.type === "subagent") {
      const label = `Subagent: ${event.name || "Subagent"}`;
      if (event.status === "started") {
        yield* this.addStep(event.subagent_id, label, "in_progress");
      } else if (event.status === "completed" || event.status === "failed") {
        yield* this.updateStep(event.subagent_id, label, event.status === "completed" ? "complete" : "error");
      }
      return;
    }

    if (event.type === "result") {
      this.resultText = event.text;
      return;
    }

    if (event.type === "error") {
      yield { type: "markdown_text", text: `Error: ${event.error || "Unknown error"}` };
      return;
    }

    if (event.type === "system" && event.subtype === "init" && event.session_id) {
      this.agentThreadId = event.session_id;
    }
  }

  *addHandoff(goal: string): Generator<StreamChunk> {
    this.activeTools.clear();
    this.lastAssistantText = "";
    this.resultText = "";
    yield* this.addStep(`handoff-${Date.now()}`, `Handed off → ${goal}`, "complete");
  }

  // ── Step window management ──────────────────────────────────────────────

  private *addStep(toolId: string, title: string, status: StepStatus): Generator<StreamChunk> {
    this.stepHistory.push({ toolId, title, status });
    if (this.stepHistory.length > MAX_VISIBLE_STEPS) {
      yield* this.emitVisibleWindow();
    } else {
      yield* this.emitSlot(this.stepHistory.length - 1);
    }
  }

  private *updateStep(toolId: string, title: string, status: StepStatus): Generator<StreamChunk> {
    const idx = this.stepHistory.findLastIndex((e) => e.toolId === toolId);
    if (idx === -1) return;
    this.stepHistory[idx].title = title;
    this.stepHistory[idx].status = status;
    yield* this.emitSlot(idx);
  }

  private *emitVisibleWindow(): Generator<StreamChunk> {
    const start = Math.max(0, this.stepHistory.length - MAX_VISIBLE_STEPS);
    for (let i = start; i < this.stepHistory.length; i++) {
      const entry = this.stepHistory[i];
      yield { type: "task_update", id: `step-${i - start}`, title: entry.title, status: entry.status };
    }
  }

  private *emitSlot(historyIndex: number): Generator<StreamChunk> {
    const windowStart = Math.max(0, this.stepHistory.length - MAX_VISIBLE_STEPS);
    const slotIndex = historyIndex - windowStart;
    if (slotIndex < 0 || slotIndex >= MAX_VISIBLE_STEPS) return;
    const entry = this.stepHistory[historyIndex];
    yield { type: "task_update", id: `step-${slotIndex}`, title: entry.title, status: entry.status };
  }
}

// ── Tool labels ───────────────────────────────────────────────────────────

const TOOL_VERBS: Record<string, [active: string, done: string]> = {
  Read: ["Reading", "Read"],
  Bash: ["Running", "Ran"],
  Grep: ["Searching", "Searched"],
  glob: ["Finding files", "Found files"],
  finder: ["Searching codebase", "Searched codebase"],
  edit_file: ["Editing", "Edited"],
  create_file: ["Creating file", "Created file"],
  Task: ["Running subtask", "Ran subtask"],
  web_search: ["Searching the web", "Searched the web"],
  read_web_page: ["Reading webpage", "Read webpage"],
  librarian: ["Researching codebase", "Researched codebase"],
  oracle: ["Consulting oracle", "Consulted oracle"],
  mermaid: ["Drawing diagram", "Drew diagram"],
  look_at: ["Analyzing file", "Analyzed file"],
  skill: ["Loading skill", "Loaded skill"],
};

function friendlyToolLabel(name: string, input: Record<string, unknown>, done?: boolean): string {
  const pair = TOOL_VERBS[name];
  const verb = pair ? pair[done ? 1 : 0] : name;
  const ctx = friendlyToolContext(name, input);
  return ctx ? `${verb} — ${ctx}` : verb;
}

function friendlyToolContext(name: string, input: Record<string, unknown>): string {
  const str = (key: string) => (typeof input[key] === "string" ? (input[key] as string) : "");
  switch (name) {
    case "Read": case "edit_file": case "create_file": case "look_at":
      return shortPath(str("path"));
    case "Bash":
      return friendlyBashContext(str("cmd"));
    case "Grep":
      return truncate(str("pattern"), 50);
    case "glob":
      return truncate(str("filePattern"), 50);
    case "finder":
      return truncate(str("query"), 60);
    case "web_search":
      return truncate(str("objective"), 60);
    case "read_web_page":
      return truncate(str("url"), 60);
    case "Task":
      return truncate(str("description"), 60);
    case "skill":
      return str("name");
    default:
      return summarizeInput(input);
  }
}

function friendlyBashContext(cmd: string): string {
  if (!cmd) return "";
  const trimmed = cmd.trim();
  const callBuiltin = trimmed.match(/^call\s+(search|sql|discover)\s+(.*)/s);
  if (callBuiltin) return `${callBuiltin[1]}: ${truncate(callBuiltin[2], 50)}`;
  const callMatch = trimmed.match(/^call\s+(\S+)\s+(\S+)/);
  if (callMatch) return `${callMatch[1]}.${callMatch[2]}`;
  return truncate(trimmed, 60);
}

function shortPath(p: string): string {
  if (!p) return "";
  const parts = p.split("/");
  return parts.length <= 3 ? p : `…/${parts.slice(-2).join("/")}`;
}

function truncate(s: string, max: number): string {
  if (!s) return "";
  const line = s.replace(/\n/g, " ").trim();
  return line.length > max ? `${line.slice(0, max)}…` : line;
}

function summarizeInput(input: Record<string, unknown>): string {
  for (const key of ["query", "pattern", "command", "cmd", "prompt", "path", "url", "message"]) {
    if (typeof input[key] === "string") return `${key}: "${input[key]}"`;
  }
  for (const [key, val] of Object.entries(input)) {
    if (typeof val === "string" && val.length > 0) return `${key}: "${val}"`;
  }
  return "";
}
