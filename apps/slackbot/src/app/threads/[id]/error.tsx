"use client";

import Link from "next/link";

export default function ThreadDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="h-[calc(100vh-41px)] flex items-center justify-center bg-zinc-950">
      <div className="text-center" role="alert" aria-live="assertive">
        <p className="text-red-400 text-sm mb-3">Failed to load thread</p>
        <p className="text-zinc-600 text-xs mb-4 max-w-sm">{error.message}</p>
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={reset}
            className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer bg-transparent border border-zinc-800 rounded-md px-3 py-1"
          >
            Retry
          </button>
          <Link
            href="/threads"
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            Back to threads
          </Link>
        </div>
      </div>
    </div>
  );
}
