import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-[var(--radius-control)] text-sm font-medium whitespace-nowrap transition-[background-color,color,border-color,box-shadow,transform,opacity] outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "border border-primary/30 bg-primary text-primary-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] hover:bg-primary/92",
        destructive:
          "border border-destructive/30 bg-destructive/14 text-destructive hover:bg-destructive/18 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40",
        outline:
          "border border-border/70 bg-background/70 shadow-none hover:bg-accent/45 hover:text-accent-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "border border-border/70 bg-card/55 text-foreground hover:bg-accent/35",
        ghost:
          "text-muted-foreground hover:bg-accent/35 hover:text-accent-foreground dark:hover:bg-accent/50",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2 has-[>svg]:px-3.5",
        xs: "h-7 gap-1 rounded-[var(--radius-control)] px-2.5 text-xs has-[>svg]:px-2 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 rounded-[var(--radius-control)] px-3 has-[>svg]:px-2.5",
        lg: "h-11 rounded-[var(--radius-control)] px-5 has-[>svg]:px-4",
        icon: "size-10",
        "icon-xs": "size-7 rounded-[var(--radius-control)] [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
