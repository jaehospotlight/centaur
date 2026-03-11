import { threadName } from "@/lib/viewer/thread-name";
import { isActiveState, isRunningState, sortThreads } from "@/lib/viewer/thread-ordering";
import type { ThreadSummary } from "@/lib/types";

export type ThreadStatusFilter = "all" | "active" | "idle" | "error";

export function parsePhaseFromMessage(message: string | undefined): string | null {
  const text = message ?? "";
  const match = text.match(/^\[([^\]]+)\]/);
  return match ? match[1].trim().toLowerCase() : null;
}

export function parseActivePhase(thread: ThreadSummary): string | null {
  return parsePhaseFromMessage(thread.last_user_message) ?? parsePhaseFromMessage(thread.first_message);
}

export function runningSubtitle(thread: ThreadSummary): string | null {
  if (!isRunningState(thread.state)) return null;
  const phase = parseActivePhase(thread);
  if (phase) return `Working on ${phase}…`;
  return "Working…";
}

export function getThreadDisplayName(thread: ThreadSummary): string {
  return thread.thread_name || threadName(thread.slack_thread_key);
}

export function matchesThreadQuery(thread: ThreadSummary, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  const haystack =
    `${thread.thread_name ?? ""} ${thread.first_message ?? ""} ${thread.last_user_message ?? ""} ${thread.slack_thread_key}`.toLowerCase();
  return haystack.includes(normalized);
}

export function matchesThreadStatus(thread: ThreadSummary, filter: ThreadStatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "active") return isActiveState(thread.state);
  if (filter === "idle") return !isActiveState(thread.state) && thread.state !== "error";
  return thread.state === filter;
}

export function filterAndSortThreads(
  threads: ThreadSummary[],
  query: string,
  filter: ThreadStatusFilter,
): ThreadSummary[] {
  return sortThreads(threads).filter((thread) => {
    return matchesThreadQuery(thread, query) && matchesThreadStatus(thread, filter);
  });
}

export function getThreadFilterCounts(threads: ThreadSummary[], query: string): Record<ThreadStatusFilter, number> {
  const filteredByQuery = threads.filter((thread) => matchesThreadQuery(thread, query));
  return {
    all: filteredByQuery.length,
    active: filteredByQuery.filter((thread) => isActiveState(thread.state)).length,
    idle: filteredByQuery.filter(
      (thread) => !isActiveState(thread.state) && thread.state !== "error",
    ).length,
    error: filteredByQuery.filter((thread) => thread.state === "error").length,
  };
}

export function sortThreadsByRecency(threads: ThreadSummary[]): ThreadSummary[] {
  return [...threads].sort((a, b) => {
    const activityDelta = (b.last_activity ?? 0) - (a.last_activity ?? 0);
    if (activityDelta !== 0) return activityDelta;

    const createdDelta = (b.created_at ?? 0) - (a.created_at ?? 0);
    if (createdDelta !== 0) return createdDelta;

    return a.slack_thread_key.localeCompare(b.slack_thread_key);
  });
}

export function pickActiveThreadHref(threads: ThreadSummary[]): string | undefined {
  const active = sortThreadsByRecency(threads).find((thread) => isActiveState(thread.state));
  return active ? `/${encodeURIComponent(active.slack_thread_key)}` : undefined;
}

export function pickLatestThreadHref(threads: ThreadSummary[]): string | undefined {
  const sorted = sortThreadsByRecency(threads);
  const candidate = sorted[0];
  return candidate ? `/${encodeURIComponent(candidate.slack_thread_key)}` : undefined;
}
