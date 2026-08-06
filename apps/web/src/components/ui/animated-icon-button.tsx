import { useRef } from "react";
import type { ComponentType, Ref } from "react";
import type { AnimatedIconHandle, AnimatedIconProps } from "@/components/icons";
import { cn } from "@/lib/utils";

type AnimatedIcon = ComponentType<AnimatedIconProps & { ref?: Ref<AnimatedIconHandle> }>;

interface AnimatedIconButtonProps {
  icon: AnimatedIcon;
  label: string;
  onClick?: () => void;
  className?: string;
  iconClassName?: string;
  children?: React.ReactNode;
}

/**
 * Botón redondo que dispara la animación del icono SIEMPRE después del click
 * (no en hover) y llama al `onClick` propio del padre.
 */
export function AnimatedIconButton({
  icon: Icon,
  label,
  onClick,
  className,
  iconClassName,
  children,
}: AnimatedIconButtonProps) {
  const ref = useRef<AnimatedIconHandle>(null);
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={() => {
        ref.current?.startAnimation();
        onClick?.();
      }}
      className={cn(
        "relative flex h-10 w-10 items-center justify-center rounded-full text-on-surface-variant transition-colors active:scale-95",
        className
      )}
    >
      <Icon ref={ref} size={20} className={cn("text-on-surface-variant", iconClassName)} />
      {children}
    </button>
  );
}