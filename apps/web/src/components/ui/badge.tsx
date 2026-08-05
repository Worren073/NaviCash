import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default: "bg-primary-fixed text-on-primary-fixed-variant",
        secondary: "bg-surface-container-highest text-on-surface-variant",
        success: "bg-status-paid/15 text-status-paid",
        pending: "bg-status-pending/15 text-status-pending",
        delayed: "bg-status-delayed/15 text-status-delayed",
        warning: "bg-status-warning/20 text-status-warning",
        income: "bg-income/15 text-income",
        expense: "bg-expense/15 text-expense",
        outline: "border border-glass-border text-on-surface-variant",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return (
    <span
      data-slot="badge"
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}

export { Badge, badgeVariants };