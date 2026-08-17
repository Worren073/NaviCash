import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { ChevronRight, X } from "lucide-react";

import { NaviAvatar } from "@/features/assistant/navi-avatar";
import { cn } from "@/lib/utils";

interface NaviTourGlobeProps {
  /** Mostrar/ocultar el globo (AnimatePresence). */
  visible: boolean;
  stepIndex: number;
  totalSteps: number;
  title: string;
  body: string;
  onNext: () => void;
  onSkip: () => void;
  /**
   * Lado de la pantalla donde está la burbuja cuando el globo va anclado
   * ("left" = burbuja a la izquierda → globo a la derecha). En modo no
   * anclado (sin burbuja, p. ej. el formulario) el globo es fijo abajo.
   */
  side?: "left" | "right";
  /** Renderizar anclado a la burbuja (posición absolute) en vez de fijo. */
  anchored?: boolean;
}

/**
 * Globo de texto del tutorial de Navi: sale de la burbuja flotante (con
 * colita) o se posiciona fijo en el pie si no hay burbuja. Estilo liquid-glass
 * acorde al chat, con título, cuerpo, contador de pasos y Siguiente/Omitir.
 */
export function NaviTourGlobe({
  visible,
  stepIndex,
  totalSteps,
  title,
  body,
  onNext,
  onSkip,
  side = "right",
  anchored = true,
}: NaviTourGlobeProps) {
  const { t } = useTranslation();
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 8, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.96 }}
          transition={{ type: "spring", stiffness: 340, damping: 28 }}
          className={cn(
            "z-40 w-[min(17rem,calc(100vw-3.5rem))]",
            anchored
              ? cn(
                  "absolute top-0",
                  side === "left" ? "left-full ml-2.5" : "right-full mr-2.5",
                )
              : "fixed bottom-40 left-1/2 -translate-x-1/2",
          )}
        >
          {/* Colita: apunta hacia la burbuja (o hacia abajo-centro en modo fijo). */}
          <span
            className={cn(
              "absolute h-3 w-3 rotate-45 rounded-[2px] border-glass-border bg-white/90",
              anchored
                ? side === "left"
                  ? "-left-1.5 top-3 border-l border-t"
                  : "-right-1.5 top-3 border-r border-t"
                : "-top-1.5 left-1/2 -translate-x-1/2 border-t border-l",
            )}
          />

          <div className="rounded-2xl border border-glass-border bg-white/90 p-4 shadow-[0_12px_40px_rgba(15,23,42,0.2)] backdrop-blur-2xl">
            <div className="flex items-start gap-2.5">
              <NaviAvatar size={28} static />
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-primary">
                  {t("assistant.name")}
                </p>
                <h3 className="text-sm font-bold leading-snug text-on-surface">{title}</h3>
              </div>
              <button
                type="button"
                aria-label={t("assistant.tour.skip")}
                onClick={onSkip}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container-high active:scale-95"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <motion.p
              key={stepIndex}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-2 text-sm leading-snug text-on-surface-variant"
            >
              {body}
            </motion.p>

            <div className="mt-3 flex items-center justify-between gap-2">
              <span className="text-xs font-medium tabular-nums text-on-surface-variant">
                {stepIndex + 1}/{totalSteps}
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onSkip}
                  className="rounded-full px-3 py-1.5 text-xs font-semibold text-on-surface-variant transition-colors hover:bg-surface-container-high active:scale-95"
                >
                  {t("assistant.tour.skip")}
                </button>
                <button
                  type="button"
                  onClick={onNext}
                  aria-label={t("assistant.tour.next")}
                  className="flex h-8 items-center gap-0.5 rounded-full bg-primary px-3 text-xs font-semibold text-on-primary shadow-sm transition-all hover:opacity-90 active:scale-95"
                >
                  {t("assistant.tour.next")}
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
