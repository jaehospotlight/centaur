"use client";

import type { CSSProperties, ReactNode, Ref, TouchEventHandler } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useThreadMotion } from "./provider";
import {
  drawerPreset,
  bottomSheetPreset,
  overlayBackdropPreset,
  sidePanelPreset,
} from "./thread-presets";

export function Presence({
  present,
  children,
}: {
  present: boolean;
  children: ReactNode;
}) {
  return <AnimatePresence initial={false}>{present ? children : null}</AnimatePresence>;
}

export function OverlayBackdrop({
  present = true,
  className,
  children,
  onClick,
}: {
  present?: boolean;
  className?: string;
  children?: ReactNode;
  onClick?: React.MouseEventHandler<HTMLDivElement>;
}) {
  const { reducedMotion } = useThreadMotion();
  const preset = overlayBackdropPreset(reducedMotion);
  return (
    <Presence present={present}>
      <motion.div
        className={className}
        initial={preset.initial}
        animate={preset.animate}
        exit={preset.exit}
        transition={preset.transition}
        onClick={onClick}
      >
        {children}
      </motion.div>
    </Presence>
  );
}

type PanelPreset = "drawer" | "bottomSheet" | "sidePanel";

export function OverlayPanel({
  preset,
  present = true,
  className,
  children,
  panelRef,
  role,
  labelledBy,
  describedBy,
  tabIndex,
  style,
  onTouchStart,
  onTouchMove,
  onTouchEnd,
}: {
  preset: PanelPreset;
  present?: boolean;
  panelRef?: Ref<HTMLDivElement>;
  className?: string;
  children?: ReactNode;
  role?: string;
  labelledBy?: string;
  describedBy?: string;
  tabIndex?: number;
  style?: CSSProperties;
  onTouchStart?: TouchEventHandler<HTMLDivElement>;
  onTouchMove?: TouchEventHandler<HTMLDivElement>;
  onTouchEnd?: TouchEventHandler<HTMLDivElement>;
}) {
  const { reducedMotion } = useThreadMotion();
  const resolved =
    preset === "drawer"
      ? drawerPreset(reducedMotion)
      : preset === "bottomSheet"
        ? bottomSheetPreset(reducedMotion)
        : sidePanelPreset(reducedMotion);

  return (
    <Presence present={present}>
      <motion.div
        ref={panelRef as never}
        className={className}
        initial={resolved.initial}
        animate={resolved.animate}
        exit={resolved.exit}
        transition={resolved.transition}
        role={role}
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        aria-modal={role === "dialog" ? true : undefined}
        tabIndex={tabIndex}
        style={style}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        {children}
      </motion.div>
    </Presence>
  );
}
