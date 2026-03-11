"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutList, MessageCircle } from "lucide-react";
import { useHaptics } from "@/components/haptics-provider";
import { useMediaQuery } from "@/hooks/use-media-query";
import { Button } from "@/components/ui/button";
import { SurfaceBar } from "@/components/ui/surface-bar";
import { cn } from "@/lib/utils";
import { useKeyboardHeight } from "@/hooks/use-visual-viewport";

type MobileTabBarProps = {
  activeThreadHref?: string;
  hasRunningAgent?: boolean;
  hasError?: boolean;
  homeSecondaryLabel?: string;
};

export function MobileTabBar({
  activeThreadHref,
  hasRunningAgent,
  hasError,
  homeSecondaryLabel,
}: MobileTabBarProps) {
  const pathname = usePathname();
  const keyboardHeight = useKeyboardHeight();
  const keyboardOpen = keyboardHeight > 0;
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const { trigger } = useHaptics();

  const isThreads = pathname === "/";
  const isCurrent = pathname.length > 1 && !pathname.startsWith("/api/");
  const primaryLabel = "Home";
  const secondaryLabel = isThreads ? (homeSecondaryLabel || "Latest") : "Current";
  if (keyboardOpen) return null;

  function scrollCurrentViewToTop() {
    const behavior: ScrollBehavior = reduceMotion ? "auto" : "smooth";
    if (isThreads) {
      const list = document.querySelector<HTMLElement>("[data-thread-list-scroll='true']");
      if (list) {
        list.scrollTo({ top: 0, behavior });
        return;
      }
    }
    if (isCurrent) {
      const feed = document.querySelector<HTMLElement>("[data-thread-feed-scroll='true']");
      if (feed) {
        feed.scrollTo({ top: 0, behavior });
        return;
      }
    }
    window.scrollTo({ top: 0, behavior });
  }

  function handleThreadsTab() {
    trigger("selection");
    if (isThreads) {
      scrollCurrentViewToTop();
      return;
    }
  }

  function handleActiveTab() {
    trigger("selection");
    if (isCurrent) {
      scrollCurrentViewToTop();
      return;
    }
  }

  const threadsClassName = cn(
    "relative flex w-full min-h-11 flex-col items-center justify-center gap-1 rounded-[var(--radius-control)] px-3 py-2 transition-colors duration-fast",
    isThreads
      ? "border border-primary/25 bg-card/95 text-foreground shadow-ring-subtle"
      : "border border-transparent text-muted-foreground hover:bg-accent/35 hover:text-foreground",
  );
  const activeClassName = cn(
    "relative flex w-full min-h-11 flex-col items-center justify-center gap-1 rounded-[var(--radius-control)] px-3 py-2 transition-colors duration-fast",
    isCurrent
      ? "border border-primary/25 bg-card/95 text-foreground shadow-ring-subtle"
      : "border border-transparent text-muted-foreground hover:bg-accent/35 hover:text-foreground",
  );
  const activeHref = activeThreadHref || "/";

  return (
    <SurfaceBar
      asChild
      className="md:hidden flex-shrink-0 flex items-center justify-center border-t border-border/70 px-3 min-h-tab-bar safe-area-bottom-sm transition-opacity-transform duration-base ease-standard"
    >
      <nav aria-label="Thread navigation">
      <div className="thread-surface grid w-full max-w-sidebar-w grid-cols-2 gap-1 rounded-[var(--radius-surface)] p-1">
      {isThreads ? (
        <Button
          type="button"
          aria-current="page"
          onClick={handleThreadsTab}
          variant="ghost"
          className={threadsClassName}
          data-touch-target
        >
          <LayoutList className="size-5" />
          <span className="text-sm font-medium">{primaryLabel}</span>
        </Button>
      ) : (
        <Link href="/" scroll={false} aria-current={undefined} onClick={() => trigger("selection")} className={threadsClassName} data-touch-target>
          {hasError && !isThreads && (
            <span className="absolute top-2 right-3 size-1.5 rounded-full bg-destructive" />
          )}
          <LayoutList className="size-5" />
          <span className="text-sm font-medium">{primaryLabel}</span>
        </Link>
      )}

      {isCurrent ? (
        <Button
          type="button"
          aria-current="page"
          onClick={handleActiveTab}
          variant="ghost"
          className={activeClassName}
          data-touch-target
        >
          {hasRunningAgent && (
            <span className="absolute top-2 right-3 size-2 rounded-full bg-primary" />
          )}
          <MessageCircle className="size-5" />
          <span className="text-sm font-medium">{secondaryLabel}</span>
        </Button>
      ) : activeThreadHref ? (
        <Link href={activeHref} scroll={false} aria-current={undefined} onClick={() => trigger("selection")} className={activeClassName} data-touch-target>
          {hasRunningAgent && (
            <span className="absolute top-2 right-3 size-2 rounded-full bg-primary" />
          )}
          <MessageCircle className="size-5" />
          <span className="text-sm font-medium">{secondaryLabel}</span>
        </Link>
      ) : (
        <Button
          type="button"
          aria-disabled="true"
          disabled
          variant="ghost"
          className={cn(activeClassName, "opacity-45")}
          data-touch-target
        >
          <MessageCircle className="size-5" />
          <span className="text-sm font-medium">{secondaryLabel}</span>
        </Button>
      )}
      </div>
    </nav></SurfaceBar>
  );
}
