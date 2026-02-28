import { useEffect, useRef, useCallback } from "react";

export function useAutoScroll<T>(dependencies: T[]) {
  const sentinelRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    const container = containerRef.current;
    if (!sentinel || !container) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        isNearBottomRef.current = entry.isIntersecting;
      },
      { root: container, rootMargin: "0px 0px 150px 0px", threshold: 0 },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, []);

  const scrollToBottom = useCallback(() => {
    if (isNearBottomRef.current && sentinelRef.current) {
      sentinelRef.current.scrollIntoView({ behavior: "auto", block: "end" });
    }
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: We want to trigger when any of the given dependencies change
  useEffect(() => {
    scrollToBottom();
  }, [...dependencies, scrollToBottom]);

  return { containerRef, sentinelRef };
}
