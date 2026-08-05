import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 active:scale-[0.98]",
  {
    variants: {
      variant: {
        default: "bg-primary text-on-primary shadow-sm hover:bg-primary/90",
        destructive: "bg-error-container text-on-error-container hover:bg-error-container/90",
        outline:
          "border border-glass-border bg-glass-surface backdrop-blur-md text-on-surface-variant hover:bg-surface-container-high",
        secondary: "bg-surface-container text-on-surface hover:bg-surface-container-high",
        ghost: "hover:bg-surface-container-high text-on-surface-variant",
        link: "text-primary underline-offset-4 hover:underline",
        glow: "relative overflow-hidden bg-primary text-on-primary shadow-[0_4px_14px_rgba(0,106,97,0.2)] hover:shadow-[0_6px_20px_rgba(0,106,97,0.3)]",
      },
      size: {
        default: "h-11 px-5 py-2.5",
        sm: "h-9 rounded-lg px-3",
        lg: "h-12 rounded-xl px-6",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };