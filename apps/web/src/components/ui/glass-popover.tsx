import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface GlassPopoverProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}

/**
 * Panel desplegable estilo "liquid glass": fondo translúcido con blur, bordes
 * redondeados y un pequeño foco de iluminación desde la esquina izquierda.
 *
 * Se ancla debajo del botón (el padre debe ser `relative`); cualquier click
 * fuera lo cierra.
 */
export function GlassPopover({ open, onClose, children, className }: GlassPopoverProps) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <div
            className="fixed inset-0 z-40"
            aria-hidden
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.96, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -4, scale: 0.97, filter: "blur(4px)" }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className={cn(
              "absolute right-0 top-full z-50 mt-2 w-80 origin-top-right overflow-hidden rounded-2xl border border-glass-border bg-white/10 shadow-[0_12px_40px_rgba(15,23,42,0.28)] backdrop-blur-2xl",
              className
            )}
            role="menu"
          >
            <div className="pointer-events-none absolute -left-10 -top-10 h-28 w-28 rounded-full bg-sky-400/40 blur-2xl" />
            <div className="pointer-events-none absolute -left-2 -top-6 h-16 w-16 rounded-full bg-primary/40 blur-xl" />
            <div className="relative">{children}</div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}