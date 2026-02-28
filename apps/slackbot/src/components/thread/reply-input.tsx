"use client";

import { useState } from "react";
import { Send } from "lucide-react";
import { postReply } from "@/app/actions/threads";

export function ReplyInput({
  threadKey,
  onSend,
}: {
  threadKey: string;
  onSend?: (message: string) => Promise<void>;
}) {
  const [isPending, setIsPending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (isPending) return;

    const form = e.currentTarget;
    const formData = new FormData(form);
    const message = (formData.get("message") as string)?.trim();
    if (!message) return;
    setError(null);
    setIsPending(true);

    try {
      if (onSend) {
        await onSend(message);
      } else {
        await postReply(threadKey, message);
      }
      form.reset();
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send reply.");
    } finally {
      setIsPending(false);
    }
  }

  if (sent) {
    return (
      <div
        className="mt-3 px-4 py-3 bg-card border border-border rounded-sm text-sm text-muted-foreground text-center"
        aria-live="polite"
      >
        Reply sent. Waiting for engineer to resume…
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-3 flex flex-col gap-2 bg-card border border-border rounded-sm p-2"
    >
      {error && (
        <p className="px-2 text-xs text-destructive" aria-live="polite">
          {error}
        </p>
      )}
      <div className="flex gap-2 items-center">
        <label htmlFor="thread-reply" className="sr-only">
          Reply message
        </label>
        <input
          id="thread-reply"
          name="message"
          type="text"
          placeholder="Type your reply…"
          disabled={isPending}
          className="flex-1 bg-background text-sm text-foreground placeholder:text-muted-foreground px-3 py-2 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-sm border border-input"
          autoComplete="off"
        />
        <button
          type="submit"
          disabled={isPending}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-primary-foreground bg-primary hover:opacity-90 rounded-sm disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          <Send className={isPending ? "size-3.5 animate-pulse" : "size-3.5"} />
          {isPending ? "Sending…" : "Send"}
        </button>
      </div>
    </form>
  );
}
