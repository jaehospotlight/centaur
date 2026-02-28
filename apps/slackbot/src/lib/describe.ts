import type { LucideIcon } from "lucide-react";
import {
  FilePlus,
  FileText,
  FolderOpen,
  GitBranch,
  Globe,
  Replace,
  SearchCode,
  SquareTerminal,
  Trash2,
  Wrench,
} from "lucide-react";

export type ToolCall = {
  id: string;
  name: string;
  input: Record<string, unknown>;
  output?: string;
  state?: "loading" | "done" | "error";
};

export type Step =
  | { type: "phase"; phase: string }
  | { type: "tool-group"; icon: LucideIcon; summary: string; category: string; calls: ToolCall[] }
  | { type: "diff"; file: string; lang: string; oldStr: string; newStr: string; result?: string }
  | { type: "terminal"; command: string; output?: string; exitCode?: number; description: string }
  | { type: "thinking"; text: string; durationS?: number }
  | { type: "error"; message: string }
  | { type: "result"; text: string; streaming?: boolean }
  | { type: "file-changes"; changes: Array<{ path: string; kind: "add" | "delete" | "update" }> };

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function getPathBasename(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function normalizeToolName(name: string): string {
  const normalized = name
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  if (normalized === "readfile") return "read_file";
  if (normalized === "writefile") return "write_file";
  if (normalized === "deletefile") return "delete_file";
  if (normalized === "grepsearch") return "grep_search";
  if (normalized === "listdir") return "list_dir";
  if (normalized === "strreplace") return "str_replace";
  return normalized;
}

export function describeToolCall(name: string, input: Record<string, unknown>): string {
  const normalized = normalizeToolName(name);

  if (normalized === "read_file" || normalized === "read") {
    return `Read ${getPathBasename(asString(input.path)) || "file"}`;
  }
  if (normalized === "write_file" || normalized === "write" || normalized === "create_file") {
    return `Created ${getPathBasename(asString(input.path)) || "file"}`;
  }
  if (normalized === "str_replace") {
    return `Edited ${getPathBasename(asString(input.path)) || "file"}`;
  }
  if (normalized === "grep_search" || normalized === "grep") {
    const query = asString(input.pattern || input.query);
    return query ? `Searched for "${query}"` : "Searched codebase";
  }
  if (normalized === "shell" || normalized === "bash" || normalized === "command_execution") {
    const command = asString(input.command);
    const first = command.split(" ").slice(0, 2).join(" ");
    return first ? `Ran ${first}` : "Ran command";
  }
  if (normalized === "list_dir" || normalized === "glob" || normalized === "list") {
    return "Listed directory contents";
  }
  if (normalized === "delete_file" || normalized === "delete") {
    return `Deleted ${getPathBasename(asString(input.path)) || "file"}`;
  }
  return `Used ${name}`;
}

export function categorizeToolCall(name: string): { icon: LucideIcon; category: string } {
  const normalized = normalizeToolName(name);
  if (normalized === "read_file" || normalized === "read") return { icon: FileText, category: "file" };
  if (normalized === "write_file" || normalized === "write" || normalized === "create_file") {
    return { icon: FilePlus, category: "write" };
  }
  if (normalized === "str_replace") return { icon: Replace, category: "edit" };
  if (normalized === "grep_search" || normalized === "grep") {
    return { icon: SearchCode, category: "search" };
  }
  if (normalized === "shell" || normalized === "bash" || normalized === "command_execution") {
    return { icon: SquareTerminal, category: "terminal" };
  }
  if (normalized === "list_dir" || normalized === "glob" || normalized === "list") {
    return { icon: FolderOpen, category: "folder" };
  }
  if (normalized === "delete_file" || normalized === "delete") return { icon: Trash2, category: "edit" };
  if (normalized.includes("git")) return { icon: GitBranch, category: "terminal" };
  if (normalized.includes("web")) return { icon: Globe, category: "web" };
  return { icon: Wrench, category: "tool" };
}

export function summarizeGroup(category: string, calls: ToolCall[]): string {
  const count = calls.length;
  if (category === "search") return "Searched codebase";
  if (category === "file") return count > 1 ? "Read files" : "Read file";
  if (category === "write") return count > 1 ? "Created files" : "Created file";
  if (category === "edit") return count > 1 ? "Edited files" : "Edited file";
  if (category === "terminal") return count > 1 ? "Ran shell commands" : "Ran shell command";
  return count > 1 ? "Used tools" : "Used tool";
}
