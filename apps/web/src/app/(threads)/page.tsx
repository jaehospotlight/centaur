"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createIdGenerator } from "ai";
import { ArrowUpRight, Menu, MessageSquarePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MessageInput } from "@/components/thread/message-input";
import { MobileTabBar } from "@/components/thread/mobile-tab-bar";
import { ThreadSummaryCard } from "@/components/thread/thread-summary-card";
import { ThreadScreenFrame } from "@/components/thread/thread-screen-frame";
import { useThreadLayout } from "@/components/thread/thread-layout";
import { useHaptics } from "@/components/haptics-provider";
import { useThreadList } from "@/hooks/use-thread-list";

export default function NewSessionPage() {
  const router = useRouter();
  const { openMobileSidebar } = useThreadLayout();
  const { trigger } = useHaptics();
  const [sending, setSending] = useState(false);
  const {
    threads,
    latestThreadHref,
    activeThreadHref,
    activeCount,
    loading,
    error,
    refreshThreads,
  } = useThreadList();
  const generateThreadId = useMemo(
    () => createIdGenerator({ prefix: "ui", size: 16 }),
    [],
  );
  const recentThreads = threads.slice(0, 4);
  const preferredThreadHref = activeThreadHref || latestThreadHref;
  const preferredThreadLabel = activeThreadHref ? "Open active" : "Open latest";
  const preferredMobileLabel = activeThreadHref ? "Active" : "Latest";

  const handleSend = useCallback(
    async (message: string) => {
      const text = message.trim();
      if (!text || sending) return;
      setSending(true);

      const threadKey = `ui:${generateThreadId()}`;
      const encoded = encodeURIComponent(threadKey);
      const messageParam = encodeURIComponent(text);
      router.push(`/${encoded}?initial_message=${messageParam}`);
    },
    [generateThreadId, router, sending],
  );

  return (
    <ThreadScreenFrame
      header={
        <div className="surface-bar border-b border-border/60 px-3 py-2 md:hidden">
          <div className="flex items-center justify-between">
            <Button
              type="button"
              onClick={() => {
                trigger("light");
                openMobileSidebar();
              }}
              variant="ghost"
              size="icon"
              className="size-10 ui-control-icon"
              aria-label="Open thread list"
              data-touch-target
            >
              <Menu className="size-5" />
            </Button>
            <span className="text-sm font-medium text-foreground">
              New Session
            </span>
            <span className="size-10" aria-hidden="true" />
          </div>
        </div>
      }
      content={
        <div className="flex min-h-0 flex-1 flex-col gap-6 md:justify-center">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
            <section className="thread-surface flex min-h-[280px] flex-col justify-center rounded-[var(--radius-shell)] px-6 py-8 md:px-8">
              <div className="max-w-xl">
                <div className="mb-4 flex size-12 items-center justify-center rounded-2xl border border-border/80 bg-card/60">
                  <MessageSquarePlus className="size-6 text-muted-foreground" />
                </div>
                <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                  Start a new thread with durable history.
                </h1>
                <p className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground">
                  New prompts start here, replies stay attached to the thread,
                  and the latest session is always one tap away.
                </p>
                <div className="mt-5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="rounded-full border border-border/70 bg-background/55 px-2.5 py-1">
                    Thread-first
                  </span>
                  <span className="rounded-full border border-border/70 bg-background/55 px-2.5 py-1">
                    Harness-agnostic
                  </span>
                  <span className="rounded-full border border-border/70 bg-background/55 px-2.5 py-1">
                    UI history persists immediately
                  </span>
                </div>
              </div>
            </section>

            <section className="thread-surface-soft rounded-[var(--radius-shell)] p-3">
              <div className="flex items-center justify-between gap-3 px-2 pb-2 pt-1">
                <div>
                  <h2 className="text-sm font-medium text-foreground">
                    Continue recent work
                  </h2>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Jump back into the most relevant thread without hunting through the sidebar.
                  </p>
                </div>
                {preferredThreadHref ? (
                  <Link
                    href={preferredThreadHref}
                    scroll={false}
                    className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-background/70 px-3 py-1.5 text-xs text-foreground thread-action-transition hover:bg-accent/45"
                  >
                    {preferredThreadLabel}
                    <ArrowUpRight className="size-3.5" />
                  </Link>
                ) : null}
              </div>
              <div className="overflow-hidden rounded-2xl border border-border/70 bg-background/35">
                {loading ? (
                  <div className="space-y-3 px-4 py-4">
                    {[0, 1, 2].map((index) => (
                      <div key={index} className="space-y-2">
                        <div className="h-3.5 w-2/3 rounded bg-secondary animate-pulse" />
                        <div className="h-3 w-5/6 rounded bg-secondary animate-pulse" />
                      </div>
                    ))}
                  </div>
                ) : error ? (
                  <div className="flex items-center justify-between gap-3 px-4 py-6">
                    <div className="text-sm text-muted-foreground">
                      Unable to load recent sessions right now.
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void refreshThreads()}
                    >
                      Retry
                    </Button>
                  </div>
                ) : recentThreads.length > 0 ? (
                  <div className="divide-y divide-border/50">
                    {recentThreads.map((thread) => (
                      <ThreadSummaryCard
                        key={thread.slack_thread_key}
                        thread={thread}
                        href={`/${encodeURIComponent(thread.slack_thread_key)}`}
                        density="compact"
                      />
                    ))}
                  </div>
                ) : (
                  <div className="px-4 py-6 text-sm text-muted-foreground">
                    Your recent sessions will appear here once you start one.
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>
      }
      footer={
        <MessageInput
          mode={sending ? "running" : "idle"}
          onSend={handleSend}
          placeholder="Start a new thread…"
          hint="The first message creates a new thread."
        />
      }
      mobileNav={
        <MobileTabBar
          activeThreadHref={preferredThreadHref}
          hasRunningAgent={activeCount > 0}
          hasError={false}
          homeSecondaryLabel={preferredMobileLabel}
        />
      }
    />
  );
}
