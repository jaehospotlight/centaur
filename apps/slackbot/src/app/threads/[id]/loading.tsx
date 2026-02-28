export default function ThreadDetailLoading() {
  return (
    <div className="h-[calc(100vh-41px)] flex flex-col bg-zinc-950 overflow-hidden">
      <div className="shrink-0 border-b border-zinc-800/50 bg-zinc-950">
        <div className="max-w-[960px] mx-auto px-5 py-3">
          <div className="flex items-center gap-2.5">
            <div className="h-4 w-4 rounded animate-shimmer" />
            <div className="h-5 w-16 rounded animate-shimmer" />
            <div className="size-[6px] bg-zinc-800 rounded-full" />
            <div className="h-3 w-12 rounded animate-shimmer" />
          </div>
        </div>
      </div>
      <div className="flex-1 min-h-0 max-w-[960px] mx-auto w-full px-5 py-4 space-y-3">
        <div className="h-3 w-full rounded animate-shimmer" />
        <div className="h-3 w-3/4 rounded animate-shimmer" />
        <div className="h-8 w-full rounded-lg animate-shimmer mt-2" />
        <div className="h-8 w-full rounded-lg animate-shimmer" />
        <div className="h-3 w-2/3 rounded animate-shimmer mt-2" />
        <div className="h-3 w-1/2 rounded animate-shimmer" />
      </div>
    </div>
  );
}
