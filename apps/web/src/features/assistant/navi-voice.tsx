import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { Mic, RefreshCw, VolumeX, X } from "lucide-react";

import { NaviAvatar } from "@/features/assistant/navi-avatar";
import type { AnimationKey } from "@/features/assistant/navi-avatar/types";
import { getSpeechProvider } from "@/features/assistant/speech";
import { useNaviVoice } from "@/features/assistant/use-navi-voice";
import { cn } from "@/lib/utils";

interface NaviVoiceProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Interfaz de voz con "Navi": overlay a pantalla completa con el fondo
 * desenfocado, la bolita de Navi en grande y la conversación visible en
 * burbujas.
 *
 * La sesión de voz vive en `useNaviVoice` (compartida con el modo compacto
 * `navi-voice-inline.tsx`). Entrada: Web Speech API en Android/desktop e iOS
 * 16.4+; en iOS sin soporte, MediaRecorder + VAD con transcripción en el
 * backend. Salida: `speechSynthesis` con arreglos para iOS.
 *
 * Se abre manteniendo presionado el botón "+" del navbar.
 */
export function NaviVoice({ open, onClose }: NaviVoiceProps) {
  const { t } = useTranslation();
  const {
    messages,
    thinking,
    phase,
    liveText,
    micErrorMessage,
    listening,
    micDenied,
    transcriptionFailed,
    relisten,
    isIOS,
  } = useNaviVoice({ active: open, relistenOnTimeout: true });
  const listRef = useRef<HTMLDivElement>(null);

  // Animación del rostro según la fase de voz.
  const voiceAnimation: AnimationKey =
    phase === "listening" || phase === "recording"
      ? "listening"
      : phase === "thinking"
        ? "thinking"
        : phase === "speaking"
          ? "happy"
          : "idle";

  // Autoscroll al fondo de la conversación.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking, open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="fixed inset-0 z-[70] flex flex-col bg-white/15 backdrop-blur-2xl"
          role="dialog"
          aria-modal="true"
          aria-label={t("assistant.voice.title")}
          // iOS: el micrófono (grabación) vuelve a bloquear el audio session;
          // cada toque del usuario re-desbloquea la salida de voz de Navi.
          onPointerDown={() => getSpeechProvider()?.warmUp()}
        >
          {/* Cerrar */}
          <button
            type="button"
            aria-label={t("common.close")}
            onClick={onClose}
            className="absolute right-5 top-[calc(env(safe-area-inset-top)+1.25rem)] z-10 flex h-11 w-11 items-center justify-center rounded-full border border-glass-border bg-glass-surface/80 text-on-surface transition-colors hover:bg-surface-container-high active:scale-95"
          >
            <X className="h-5 w-5" />
          </button>

          {/* Conversación en burbujas (se mantiene mientras Navi pregunta) */}
          <div ref={listRef} className="mx-auto mt-20 w-full max-w-md flex-1 space-y-3 overflow-y-auto px-5 pb-4">
            {messages.map((m) => (
              <div
                key={m.id}
                className={cn(
                  "max-w-[85%] whitespace-pre-line rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                  m.role === "user"
                    ? "ml-auto rounded-br-sm bg-primary text-on-primary shadow-sm"
                    : "mr-auto rounded-bl-sm bg-surface-container-high text-on-surface"
                )}
              >
                {m.text}
              </div>
            ))}
            {thinking && (
              <div className="mr-auto flex items-center gap-1.5 rounded-2xl rounded-bl-sm bg-surface-container-high px-3.5 py-2.5">
                {[0, 1, 2].map((i) => (
                  <motion.span
                    key={i}
                    className="h-1.5 w-1.5 rounded-full bg-on-surface-variant"
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Bolita de Navi en grande */}
          <motion.div
            key={phase}
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 260, damping: 24 }}
            className="relative flex h-[180px] w-[180px] shrink-0 items-center justify-center self-center"
          >
            {listening && (
              <>
                <motion.span
                  className="absolute inset-0 rounded-full border border-sky-400/60"
                  animate={{ scale: [1, 1.12], opacity: [0.8, 0] }}
                  transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
                />
                <motion.span
                  className="absolute inset-0 rounded-full border border-sky-400/50"
                  animate={{ scale: [1, 1.12], opacity: [0.8, 0] }}
                  transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut", delay: 0.5 }}
                />
              </>
            )}
            {phase === "micError" && (
              <motion.span
                className="absolute inset-0 rounded-full border border-status-delayed/60"
                animate={{ scale: [1, 1.12], opacity: [0.8, 0] }}
                transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
              />
            )}
            {phase === "idle" && (
              <motion.span
                className="absolute inset-0 rounded-full border border-sky-400/30"
                animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 2.4, repeat: Infinity }}
              />
            )}
            <button
              type="button"
              aria-label={t("assistant.voice.talkAgain")}
              onClick={relisten}
              className="relative rounded-full focus-visible:outline-none disabled:cursor-not-allowed"
              style={{ touchAction: "none" }}
              disabled={phase === "thinking" || phase === "micError"}
            >
              <NaviAvatar size={180} animation={voiceAnimation} />
            </button>
          </motion.div>

          {/* Estado */}
          <div className="flex shrink-0 flex-col items-center gap-2 pb-4 pt-5">
            {phase === "unsupported" ? (
              <p className="text-sm text-on-surface-variant">{t("assistant.voice.unsupported")}</p>
            ) : phase === "micError" ? (
              <p className="max-w-xs text-center text-sm text-on-surface-variant">
                {micErrorMessage ??
                  (micDenied
                    ? t("assistant.voice.micDenied")
                    : transcriptionFailed
                      ? t("assistant.voice.transcriptionError")
                      : t("assistant.voice.micError"))}
              </p>
            ) : (
              <p className="text-sm text-on-surface-variant">
                {listening && liveText
                  ? liveText
                  : phase === "listening"
                    ? t("assistant.voice.listening")
                    : phase === "recording"
                      ? t("assistant.voice.recording")
                      : phase === "thinking"
                        ? t("assistant.voice.thinking")
                        : phase === "speaking"
                          ? t("assistant.voice.speaking")
                          : t("assistant.voice.talkAgain")}
              </p>
            )}
            {(phase === "idle" || phase === "micError") && (
              <button
                type="button"
                aria-label={phase === "micError" ? t("assistant.voice.retry") : t("assistant.voice.talkAgain")}
                onClick={relisten}
                className="mt-2 flex h-11 w-11 items-center justify-center rounded-full bg-primary text-on-primary shadow-sm transition-all hover:opacity-90 active:scale-90"
              >
                {phase === "micError" ? (
                  <RefreshCw className="h-5 w-5" />
                ) : (
                  <Mic className="h-5 w-5" />
                )}
              </button>
            )}
          </div>

          {/* iOS: recordatorio del interruptor de silencio (silencio TTS) */}
          {isIOS && (
            <div className="flex shrink-0 items-center justify-center gap-1.5 px-6 pb-2 text-center">
              <VolumeX className="h-3.5 w-3.5 shrink-0 text-on-surface-variant" />
              <p className="text-[11px] leading-snug text-on-surface-variant">
                {t("assistant.voice.silentMode")}
              </p>
            </div>
          )}

          {/* Aviso legal: Navi no es asesor financiero */}
          <div className="shrink-0 px-6 pb-6 text-center">
            <p className="text-xs leading-snug text-on-surface-variant">{t("assistant.disclaimer")}</p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
