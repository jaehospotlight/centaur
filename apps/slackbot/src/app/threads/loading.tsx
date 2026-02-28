export default function ThreadsLoading() {
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-200 font-sans px-8 py-8 max-w-[1200px] mx-auto">
      <div className="flex justify-between items-center mb-6 pb-4 border-b border-zinc-800/50">
        <div>
          <div className="h-5 w-20 rounded animate-shimmer" />
          <div className="h-3 w-28 rounded mt-2 animate-shimmer" />
        </div>
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(360px,1fr))] gap-2.5">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="bg-zinc-900/30 border border-zinc-800/50 rounded-lg p-4 space-y-3"
          >
            <div className="flex justify-between">
              <div className="h-5 w-24 rounded animate-shimmer" />
              <div className="h-3 w-10 rounded animate-shimmer" />
            </div>
            <div className="h-3 w-40 rounded animate-shimmer" />
            <div className="h-3 w-24 rounded animate-shimmer" />
          </div>
        ))}
      </div>
    </main>
  );
}
