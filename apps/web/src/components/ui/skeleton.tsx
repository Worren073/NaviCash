import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn(
        "skeleton-shimmer animate-pulse rounded-lg bg-surface-container-highest",
        className
      )}
      {...props}
    />
  );
}

export { Skeleton };