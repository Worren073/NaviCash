import { motion } from "motion/react";

import { cn } from "@/lib/utils";

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  layoutId,
  size = "md",
  disabled = false,
  scrollable = false,
}: {
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (value: T) => void;
  layoutId: string;
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  /** Permite desplazar horizontalmente las opciones cuando no caben en el ancho disponible (móvil). */
  scrollable?: boolean;
}) {
  const padBySize = {
    sm: "px-3 py-1.5 text-xs",
    md: "px-4 py-2 text-sm",
    lg: "px-5 py-3 text-base",
  } as const;
  return (
    <div
      className={cn(
        "flex rounded-full border border-glass-border bg-surface-container-highest p-1",
        size === "lg" && "p-1.5",
        disabled && "opacity-70",
        scrollable && "max-w-full overflow-x-auto scrollbar-hide",
      )}
    >
      {options.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            aria-pressed={active}
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={cn(
              "relative flex-1 rounded-full font-medium transition-colors",
              scrollable && "shrink-0",
              padBySize[size],
              active ? "text-white" : "text-on-surface-variant"
            )}
          >
            {active && (
              <motion.span
                layoutId={layoutId}
                transition={{ type: "spring", stiffness: 400, damping: 32 }}
                className="absolute inset-0 rounded-full bg-primary shadow-[0_2px_8px_rgba(0,106,97,0.2)]"
              />
            )}
            <span className="relative z-10">{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
