import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Envuelve contenido y lo muestra desenfocado mientras `loading` es true,
 * con un pulso sutil; al terminar la carga hace focus con transición.
 */
export function BlurLoading({
  loading,
  className,
  children,
}: {
  loading: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      aria-busy={loading}
      className={cn(
        loading ? "page-loading-blur" : "page-loading-ready",
        className
      )}
    >
      {children}
    </div>
  );
}

/** Pantalla de carga inicial con el logo de la app. */
export function Splash() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4">
      <div className="splash-fade-out flex flex-col items-center gap-3">
        <div className="flex h-16 w-16 animate-pulse items-center justify-center rounded-3xl bg-primary text-3xl font-bold text-on-primary shadow-lg shadow-primary/30">
          N
        </div>
        <p className="text-sm font-medium text-on-surface-variant">Cargando…</p>
      </div>
    </div>
  );
}