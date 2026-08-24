import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex min-h-6 w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold tracking-[0.01em]",
  {
    variants: {
      variant: {
        default: "bg-foreground text-background",
        outline: "border border-border bg-surface text-muted-foreground",
        warm: "bg-primary text-primary-foreground",
        success:
          "bg-[color-mix(in_oklch,var(--success)_14%,var(--surface))] text-[oklch(38%_0.1_147)]",
        danger:
          "bg-[color-mix(in_oklch,var(--danger)_12%,var(--surface))] text-[oklch(45%_0.15_27)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
