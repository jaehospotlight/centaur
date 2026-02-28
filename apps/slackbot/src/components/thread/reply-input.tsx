"use client";

import { useState } from "react";
import { postReply } from "@/app/actions/threads";

export function ReplyInput({ threadKey }: { threadKey: string }) {
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
      await postReply(threadKey, message);
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
        className="mt-4 px-4 py-3 bg-surface border border-zinc-800/50 rounded-lg text-sm text-zinc-500 text-center animate-fade-in"
        aria-live="polite"
      >
        Reply sent. Waiting for engineer to resume…
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-4 flex flex-col gap-2 bg-surface border border-zinc-800/50 rounded-lg p-2 animate-fade-in"
    >
      {error && (
        <p className="px-2 text-xs text-red-400" aria-live="polite">
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
        className="flex-1 bg-transparent text-sm text-zinc-300 placeholder:text-zinc-700 px-3 py-2 transition-opacity duration-200 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-500 rounded-md"
        autoComplete="off"
      />
      <button
        type="submit"
        disabled={isPending}
        className="px-4 py-2 text-sm font-medium text-zinc-300 bg-zinc-800 hover:bg-zinc-700 rounded-md transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
      >
        {isPending ? "Sending…" : "Send"}
      </button>
      </div>
    </form>
  );
}
