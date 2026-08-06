import { Check, X } from "lucide-react";

import { cn } from "@/lib/utils";

interface FieldHintProps {
  ok?: boolean;
  children: string;
  className?: string;
}

/** Hint bajo un input: ✓ verde si `ok`, ✗ gris/rojo si no cumple. */
export function FieldHint({ ok, children, className }: FieldHintProps) {
  return (
    <p
      className={cn(
        "flex items-center gap-1.5 text-xs",
        ok ? "text-income" : "text-on-surface-variant",
        className
      )}
    >
      {ok ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}
      {children}
    </p>
  );
}