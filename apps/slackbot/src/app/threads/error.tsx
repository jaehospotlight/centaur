"use client";

export default function ThreadsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center" role="alert" aria-live="assertive">
        <p className="text-red-400 text-sm mb-3">Something went wrong</p>
        <p className="text-zinc-600 text-xs mb-4 max-w-sm">{error.message}</p>
        <button
          onClick={reset}
          className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer bg-transparent border border-zinc-800 rounded-md px-3 py-1"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
