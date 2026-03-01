"use client";

import type { SVGProps } from "react";
import { cn } from "@/lib/utils";

type IconProps = SVGProps<SVGSVGElement> & {
  className?: string;
  title?: string;
};

function BaseIcon({ className, title, children, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("size-4", className)}
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      {...props}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

export function AgentRunIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="12" cy="12" r="2.2" />
      <path d="M12 4.5a7.5 7.5 0 1 1-7.5 7.5" />
      <path d="M12 19.5a7.5 7.5 0 0 1-7.5-7.5" opacity="0.5" />
    </BaseIcon>
  );
}

export function CompactDensityIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M5 7h14" />
      <path d="M7 12h10" />
      <path d="M9 17h6" />
      <path d="M5 6v2M7 11v2M9 16v2" opacity="0.55" />
    </BaseIcon>
  );
}

export function ThreadContextIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4.5 6.5a2.5 2.5 0 0 1 2.5-2.5h10a2.5 2.5 0 0 1 2.5 2.5v6a2.5 2.5 0 0 1-2.5 2.5H10l-3.5 3v-3H7a2.5 2.5 0 0 1-2.5-2.5z" />
      <path d="M8 8.5h8M8 11.5h5" opacity="0.6" />
    </BaseIcon>
  );
}

export function ToolArgumentsIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M8 6.5H6v11h2" />
      <path d="M16 6.5h2v11h-2" />
      <circle cx="12" cy="9" r="1.2" />
      <circle cx="12" cy="12" r="1.2" />
      <circle cx="12" cy="15" r="1.2" />
    </BaseIcon>
  );
}

export function CommandSurfaceIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect x="4.5" y="4.5" width="15" height="15" rx="3" />
      <path d="M8.5 10.5h7M8.5 13.5h4" opacity="0.65" />
    </BaseIcon>
  );
}
