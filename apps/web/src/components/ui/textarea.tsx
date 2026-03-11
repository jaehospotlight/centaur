import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-20 w-full rounded-[var(--radius-control)] border border-input/75 bg-card/45 px-3.5 py-2.5 text-base shadow-none transition-[color,box-shadow,border-color,background-color] outline-none placeholder:text-muted-foreground/75 focus-visible:border-ring focus-visible:bg-card/65 focus-visible:ring-2 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/25 dark:aria-invalid:ring-destructive/40",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
