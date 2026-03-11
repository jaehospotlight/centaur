import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1.5 overflow-hidden rounded-full border border-transparent px-2.5 py-1 text-[11px] font-medium whitespace-nowrap transition-[color,box-shadow,border-color,background-color] focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3.5",
  {
    variants: {
      variant: {
        default: "border-primary/30 bg-primary/12 text-primary [a&]:hover:bg-primary/18",
        secondary:
          "border-border/70 bg-card/55 text-foreground [a&]:hover:bg-accent/40",
        destructive:
          "border-destructive/30 bg-destructive/12 text-destructive focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 [a&]:hover:bg-destructive/18",
        outline:
          "border-border/70 bg-background/60 text-foreground [a&]:hover:bg-accent/35 [a&]:hover:text-accent-foreground",
        ghost: "[a&]:hover:bg-accent [a&]:hover:text-accent-foreground",
        link: "text-primary underline-offset-4 [a&]:hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
