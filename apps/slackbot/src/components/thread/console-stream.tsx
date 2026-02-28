"use client";

import type { Turn } from "@/lib/types";
import { EventView } from "./event-view";
import { MarkdownView } from "./markdown-view";
import { useAutoScroll } from "@/hooks/use-auto-scroll";

function PhaseDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="h-px flex-1 bg-zinc-800/50" />
      <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-600 shrink-0">
        {label}
      </span>
      <div className="h-px flex-1 bg-zinc-800/50" />
    </div>
  );
}

function UserMessage({ text }: { text: string }) {
  return (
    <div className="py-1">
      <span className="text-zinc-300 text-sm">{text}</span>
    </div>
  );
}

function parsePhaseFromMessage(msg: string | null | undefined): { phase: string | null; text: string } {
  const safe = msg ?? "";
  if (!safe) return { phase: null, text: "" };
  const match = safe.match(/^\[(\w+)\]\s*(.*)/);
  if (match) return { phase: match[1].toUpperCase(), text: match[2] };
  return { phase: null, text: safe };
}

export function ConsoleStream({
  turns,
  state,
}: {
  turns: Turn[];
  state?: string;
}) {
  const { containerRef, sentinelRef } = useAutoScroll([turns]);

  const items: Array<{ key: string; node: React.ReactNode }> = [];

  for (const turn of turns) {
    const { phase, text } = parsePhaseFromMessage(turn.user_message);

    if (phase) {
      items.push({
        key: `phase-${turn.turn_id}`,
        node: <PhaseDivider label={phase} />,
      });
    }

    if (text) {
      items.push({
        key: `user-${turn.turn_id}`,
        node: <UserMessage text={text} />,
      });
    }

    const events = Array.isArray(turn.events) ? turn.events : [];
    for (let i = 0; i < events.length; i++) {
      items.push({
        key: `ev-${turn.turn_id}-${i}`,
        node: <EventView event={events[i]} />,
      });
    }

    const hasResultInEvents = events.some(
      (e) =>
        (e.type === "result" && (e as { result?: string }).result) ||
        (e.type === "item.completed" && (e as { item?: { text?: string } }).item?.text)
    );
    if (turn.result && !hasResultInEvents) {
      items.push({
        key: `result-${turn.turn_id}`,
        node: (
          <div className="py-1">
            <div className="text-sm leading-relaxed text-zinc-300">
              <MarkdownView text={turn.result} />
            </div>
          </div>
        ),
      });
    }
  }

  return (
    <div
      ref={containerRef}
      role="log"
      aria-live="polite"
      aria-atomic="false"
      className="flex-1 overflow-y-auto min-h-0 px-5 py-3 space-y-0.5"
    >
      {items.length === 0 && (
        <div className="flex items-center justify-center h-full text-zinc-700 text-sm">
          {state === "idle"
            ? "No events yet. This thread is idle."
            : "Waiting for events…"}
        </div>
      )}
      {items.map((item) => (
        <div key={item.key} className="console-item animate-fade-in">{item.node}</div>
      ))}
      <div ref={sentinelRef} className="h-px" />
    </div>
  );
}
