"use client";

import type { ReactNode, Ref, TouchEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { OverlayBackdrop, OverlayPanel } from "@/motion/primitives";
import { useHaptics } from "@/components/haptics-provider";
import { cn } from "@/lib/utils";

type ResponsivePanelSide = "left" | "right" | "bottom";

export function ResponsivePanel({
  open,
  side,
  onClose,
  className,
  children,
  labelledBy,
  describedBy,
  panelRef,
  dismissibleByDrag = false,
  mobileOnly = false,
}: {
  open: boolean;
  side: ResponsivePanelSide;
  onClose: () => void;
  className?: string;
  children: ReactNode;
  labelledBy?: string;
  describedBy?: string;
  panelRef?: Ref<HTMLDivElement>;
  dismissibleByDrag?: boolean;
  mobileOnly?: boolean;
}) {
  const internalPanelRef = useRef<HTMLDivElement | null>(null);
  const previousFocusedRef = useRef<HTMLElement | null>(null);
  const dragStartRef = useRef<number | null>(null);
  const dragCrossStartRef = useRef<number | null>(null);
  const dragPendingRef = useRef(0);
  const dragRafRef = useRef<number>(0);
  const draggingRef = useRef(false);
  const [dragOffset, setDragOffset] = useState(0);
  const { trigger } = useHaptics();

  const setCombinedRef = useCallback(
    (node: HTMLDivElement | null) => {
      internalPanelRef.current = node;
      if (!panelRef) return;
      if (typeof panelRef === "function") {
        panelRef(node);
        return;
      }
      (panelRef as { current: HTMLDivElement | null }).current = node;
    },
    [panelRef],
  );

  const handleTouchStart = useCallback(
    (event: TouchEvent<HTMLDivElement>) => {
      if ((side !== "bottom" && side !== "left") || !dismissibleByDrag) return;
      const panel = internalPanelRef.current;
      if (!panel) return;
      if (side === "bottom") {
        const touchY = event.touches[0].clientY;
        const fromTop = touchY - panel.getBoundingClientRect().top;
        if (panel.scrollTop > 0 || fromTop > 80) {
          dragStartRef.current = null;
          draggingRef.current = false;
          return;
        }
        dragStartRef.current = touchY;
        dragCrossStartRef.current = event.touches[0].clientX;
      } else {
        const panelRect = panel.getBoundingClientRect();
        const touchX = event.touches[0].clientX;
        const fromRight = panelRect.right - touchX;
        if (fromRight > 48) {
          dragStartRef.current = null;
          dragCrossStartRef.current = null;
          draggingRef.current = false;
          return;
        }
        dragStartRef.current = touchX;
        dragCrossStartRef.current = event.touches[0].clientY;
      }
      draggingRef.current = true;
    },
    [dismissibleByDrag, side],
  );

  const handleTouchMove = useCallback(
    (event: TouchEvent<HTMLDivElement>) => {
      if (
        dragStartRef.current === null ||
        dragCrossStartRef.current === null ||
        !draggingRef.current
      ) {
        return;
      }
      const currentPrimary = side === "left" ? event.touches[0].clientX : event.touches[0].clientY;
      const currentCross = side === "left" ? event.touches[0].clientY : event.touches[0].clientX;
      const delta =
        side === "left"
          ? dragStartRef.current - currentPrimary
          : currentPrimary - dragStartRef.current;
      const crossDelta = Math.abs(currentCross - dragCrossStartRef.current);
      if (delta <= 0 || crossDelta > delta) return;
      event.preventDefault();
      dragPendingRef.current = delta;
      if (dragRafRef.current) return;
      dragRafRef.current = window.requestAnimationFrame(() => {
        dragRafRef.current = 0;
        setDragOffset(dragPendingRef.current);
      });
    },
    [side],
  );

  const handleTouchEnd = useCallback(() => {
    const finalDragOffset = Math.max(dragOffset, dragPendingRef.current);
    if (dragRafRef.current) {
      window.cancelAnimationFrame(dragRafRef.current);
      dragRafRef.current = 0;
    }
    if (finalDragOffset > 100) {
      trigger("light");
      onClose();
    }
    setDragOffset(0);
    dragStartRef.current = null;
    dragCrossStartRef.current = null;
    dragPendingRef.current = 0;
    draggingRef.current = false;
  }, [dragOffset, onClose, trigger]);

  useEffect(() => {
    return () => {
      if (dragRafRef.current) {
        window.cancelAnimationFrame(dragRafRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!open) {
      setDragOffset(0);
      return;
    }
    const panel = internalPanelRef.current;
    previousFocusedRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusFirst = () => {
      if (!panel) return;
      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(
          "button,[href],input,select,textarea,[tabindex]:not([tabindex='-1'])",
        ),
      ).filter((node) => !node.hasAttribute("disabled"));
      (focusable[0] ?? panel).focus();
    };

    window.requestAnimationFrame(focusFirst);

    const onKeyDown = (event: KeyboardEvent) => {
      if (!panel) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(
          "button,[href],input,select,textarea,[tabindex]:not([tabindex='-1'])",
        ),
      ).filter((node) => !node.hasAttribute("disabled"));
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const inside = !!(active && panel.contains(active));
      if (event.shiftKey) {
        if (!inside || active === first) {
          event.preventDefault();
          last.focus();
        }
        return;
      }
      if (!inside || active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocusedRef.current?.focus();
      previousFocusedRef.current = null;
      setDragOffset(0);
      dragCrossStartRef.current = null;
    };
  }, [onClose, open]);

  if (!open) return null;

  const preset = side === "bottom" ? "bottomSheet" : side === "left" ? "drawer" : "sidePanel";
  const panelClassName =
    side === "bottom"
      ? "absolute inset-x-0 bottom-0 max-h-[82dvh] overflow-y-auto overscroll-contain rounded-t-[var(--radius-shell)] border-t border-border/80 thread-surface-overlay shadow-sheet"
      : side === "left"
        ? "absolute inset-y-0 left-0 flex w-[332px] max-w-[92vw] flex-col overflow-y-auto overscroll-contain border-r border-border/80 thread-surface-sidebar shadow-dialog"
        : "absolute inset-y-0 right-0 flex w-full max-w-[520px] flex-col overflow-y-auto overscroll-contain border-l border-border/80 thread-surface-overlay shadow-dialog";

  return (
    <div className={cn("fixed inset-0 z-50", mobileOnly && "md:hidden")} aria-hidden={open ? undefined : true}>
      <OverlayBackdrop
        present={open}
        className="absolute inset-0 bg-black/60 backdrop-blur-[2px]"
        onClick={() => {
          trigger("light");
          onClose();
        }}
      />
      <OverlayPanel
        present={open}
        preset={preset}
        panelRef={setCombinedRef}
        role="dialog"
        labelledBy={labelledBy}
        describedBy={describedBy}
        className={cn(panelClassName, className)}
        tabIndex={-1}
        style={
          dragOffset > 0
            ? side === "left"
              ? { transform: `translateX(-${dragOffset}px)` }
              : { transform: `translateY(${dragOffset}px)` }
            : undefined
        }
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {children}
      </OverlayPanel>
    </div>
  );
}
