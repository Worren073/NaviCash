import { cn } from "@/lib/utils";

/**
 * Luces decorativas tipo "liquid glass": focos desenfocados en las esquinas
 * superior izquierda e inferior derecha, con un resplandor central suave que
 * simula luz viajando entre ambas esquinas.
 *
 * Usa `color` (hex) para teñir las luces del color de la tarjeta. El padre
 * debe tener `relative overflow-hidden`.
 */
export function CardGlow({ color, className }: { color: string; className?: string }) {
  return (
    <>
      <div
        aria-hidden
        className={cn("pointer-events-none absolute -left-10 -top-10 h-28 w-28 rounded-full blur-2xl", className)}
        style={{ backgroundColor: `${color}40` }}
      />
      <div
        aria-hidden
        className={cn("pointer-events-none absolute -left-2 -top-6 h-16 w-16 rounded-full blur-xl", className)}
        style={{ backgroundColor: `${color}40` }}
      />
      <div
        aria-hidden
        className={cn("pointer-events-none absolute -right-10 -bottom-10 h-28 w-28 rounded-full blur-2xl", className)}
        style={{ backgroundColor: `${color}30` }}
      />
      <div
        aria-hidden
        className={cn("pointer-events-none absolute -right-2 -bottom-6 h-16 w-16 rounded-full blur-xl", className)}
        style={{ backgroundColor: `${color}30` }}
      />
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute left-1/2 top-1/2 h-16 w-40 -translate-x-1/2 -translate-y-1/2 rounded-full blur-2xl",
          className
        )}
        style={{ backgroundColor: `${color}15` }}
      />
    </>
  );
}
