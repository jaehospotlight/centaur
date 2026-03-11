"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function ThreadScreenFrame({
  header,
  banner,
  content,
  footer,
  mobileNav,
  overlay,
  className,
}: {
  header?: ReactNode;
  banner?: ReactNode;
  content: ReactNode;
  footer?: ReactNode;
  mobileNav?: ReactNode;
  overlay?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("app-shell h-dvh md:h-full flex flex-col bg-background overflow-hidden", className)}>
      {header}
      {banner}
      <div className="mx-auto flex min-h-0 w-full max-w-[1040px] flex-1 flex-col px-3 py-3 safe-area-inset-x md:px-6 md:py-5">
        {content}
      </div>
      {footer}
      {mobileNav}
      {overlay}
    </div>
  );
}
