import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { Mic } from "lucide-react";

import { useNaviVoice } from "@/features/assistant/use-navi-voice";
import type { VoicePhase } from "@/features/assistant/use-navi-voice";
import { cn } from "@/lib/utils";

export interface NaviVoiceInlineHandle {
  /** Finaliza la captura en curso (push-to-talk: al soltar). */
  stop: () => void;
  /** Aborta la captura sin resultado y corta el TTS. */
  cancel: () => void;
}

interface NaviVoiceInlineProps {
  active: boolean;
  /** Lado de la pantalla donde está el orbe: la burbujita sale al lado opuesto. */
  side: "left" | "right";
  onClose: () => void;
  /** Notifica la fase de voz para animar el orbe flotante. */
  onPhaseChange?: (phase: VoicePhase) => void;
}

/**
 * Modo de voz compacto de "Navi": burbujitas ancladas al orbe flotante
 * (micrófono animado → 3 puntos → respuesta) sin tapar la vista actual.
 *
 * Se abre manteniendo presionada la burbuja; al soltar, Navi piensa y responde
 * en voz alta (push-to-talk). Comparte la sesión de voz con el overlay
 * (`useNaviVoice`) y se cierra sola tras leer la respuesta (o al tocar el orbe).
 */
export const NaviVoiceInline = forwardRef<NaviVoiceInlineHandle, NaviVoiceInlineProps>(
  function NaviVoiceInline({ active, side, onClose, onPhaseChange }, ref) {
    const { t } = useTranslation();
    const {
      messages,
      phase,
      liveText,
      micErrorMessage,
      listening,
      micDenied,
      transcriptionFailed,
      stop,
      cancel,
    } = useNaviVoice({ active, relistenOnTimeout: false });

    useImperativeHandle(ref, () => ({ stop, cancel }), [stop, cancel]);

    // Reporta la fase al orbe para su animación.
    useEffect(() => {
      onPhaseChange?.(phase);
    }, [phase, onPhaseChange]);

    // Autocierre: tras la respuesta (idle) o ante un estado terminal.
    const startedRef = useRef(false);
    useEffect(() => {
      if (!active) {
        startedRef.current = false;
        return;
      }
      if (phase !== "idle") {
        startedRef.current = true;
        return;
      }
    }, [phase, active]);

    useEffect(() => {
      if (!active) return;
      const terminal =
        phase === "idle"
          ? startedRef.current
          : phase === "unsupported" || phase === "micError";
      if (!terminal) return;
      // Al terminar de hablar, el cuadro se quita de inmediato.
      if (phase === "idle") {
        onClose();
        return;
      }
      // Estados de error: se deja leer el mensaje un momento.
      const id = window.setTimeout(onClose, 2800);
      return () => window.clearTimeout(id);
    }, [phase, active, onClose]);

    const last = messages[messages.length - 1];
    const errorText = micErrorMessage
      ? micErrorMessage
      : micDenied
        ? t("assistant.voice.micDenied")
        : transcriptionFailed
          ? t("assistant.voice.transcriptionError")
          : t("assistant.voice.micError");

    const contentKey =
      phase === "thinking"
        ? "thinking"
        : phase === "speaking"
          ? "speaking"
          : phase === "unsupported" || phase === "micError"
            ? "error"
            : "listening";

    return (
      <AnimatePresence>
        {active && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.94 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.94 }}
            transition={{ type: "spring", stiffness: 340, damping: 28 }}
            className={cn(
              "pointer-events-none absolute top-1/2 z-50 w-[min(15rem,calc(100vw-4rem))] -translate-y-1/2",
              side === "left" ? "left-full ml-2.5" : "right-full mr-2.5",
            )}
            aria-live="polite"
          >
            {/* Colita hacia el orbe */}
            <span
              className={cn(
                "absolute top-1/2 h-3 w-3 -translate-y-1/2 rotate-45 rounded-[2px] border-glass-border bg-white/90",
                side === "left" ? "-left-1.5 border-l border-t" : "-right-1.5 border-r border-t",
              )}
            />

            <div className="rounded-2xl border border-glass-border bg-white/90 px-3.5 py-2.5 shadow-[0_12px_40px_rgba(15,23,42,0.2)] backdrop-blur-2xl">
              <AnimatePresence mode="wait" initial={false}>
                {contentKey === "listening" && (
                  <motion.div
                    key="listening"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="flex items-center gap-2.5"
                  >
                    <span className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-on-primary">
                      <Mic className="h-4 w-4" />
                      <motion.span
                        className="absolute inset-0 rounded-full border border-primary/60"
                        animate={{ scale: [1, 1.55], opacity: [0.6, 0] }}
                        transition={{ duration: 1.2, repeat: Infinity, ease: "easeOut" }}
                      />
                    </span>
                    <span className="min-w-0 flex-1 truncate text-xs font-medium text-on-surface-variant">
                      {liveText ||
                        (listening ? t("assistant.voice.releaseToSend") : t("assistant.voice.listening"))}
                    </span>
                  </motion.div>
                )}

                {contentKey === "thinking" && (
                  <motion.div
                    key="thinking"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="flex items-center gap-2"
                  >
                    <span className="flex items-center gap-1.5">
                      {[0, 1, 2].map((i) => (
                        <motion.span
                          key={i}
                          className="h-2 w-2 rounded-full bg-on-surface-variant"
                          animate={{ opacity: [0.3, 1, 0.3], y: [0, -3, 0] }}
                          transition={{ duration: 1, repeat: Infinity, delay: i * 0.18 }}
                        />
                      ))}
                    </span>
                    <span className="text-xs font-medium text-on-surface-variant">
                      {t("assistant.voice.thinking")}
                    </span>
                  </motion.div>
                )}

                {contentKey === "speaking" && (
                  <motion.p
                    key="speaking"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="line-clamp-4 text-xs leading-snug text-on-surface"
                  >
                    {last?.role === "assistant" ? last.text : t("assistant.voice.speaking")}
                  </motion.p>
                )}

                {contentKey === "error" && (
                  <motion.p
                    key="error"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="text-xs leading-snug text-on-surface-variant"
                  >
                    {phase === "unsupported" ? t("assistant.voice.unsupported") : errorText}
                  </motion.p>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    );
  },
);
