import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { Mic, RefreshCw, X } from "lucide-react";

import { useAssistant } from "@/hooks/use-assistant";
import { NaviAvatar } from "@/features/assistant/navi-avatar";
import {
  getRecognitionKind,
  getRecognitionProvider,
  getSpeechProvider,
} from "@/features/assistant/speech";
import type { RecognitionErrorCode } from "@/features/assistant/speech/types";
import { cn } from "@/lib/utils";

type VoicePhase =
  | "listening"
  | "recording"
  | "thinking"
  | "speaking"
  | "idle"
  | "unsupported"
  | "micError";

interface NaviVoiceProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Interfaz de voz con "Navi": overlay a pantalla completa con el fondo
 * desenfocado, la bolita de Navi en grande y la conversación visible en
 * burbujas.
 *
 * Entrada de voz:
 * - Android/desktop → Web Speech API (escucha → envía el texto al backend).
 * - iOS → grabación con MediaRecorder + corte por silencio (VAD) y
 *   transcripción en el backend (`/api/assistant/transcribe`).
 *
 * Salida (TTS): ``speechSynthesis`` nativo con arreglos para iOS (warm-up del
 * audio session en el gesto y carga de voces vía ``voiceschanged``).
 *
 * Se abre manteniendo presionado el botón "+" del navbar.
 */
export function NaviVoice({ open, onClose }: NaviVoiceProps) {
  const { t } = useTranslation();
  const { messages, thinking, send, abort } = useAssistant();
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [micErrorCode, setMicErrorCode] = useState<RecognitionErrorCode | null>(null);
  const [micErrorMessage, setMicErrorMessage] = useState<string | null>(null);
  const [liveText, setLiveText] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const recRef = useRef<ReturnType<typeof getRecognitionProvider>>(null);
  const speechRef = useRef<ReturnType<typeof getSpeechProvider>>(null);
  const mountedRef = useRef(false);
  const lastCountRef = useRef(0);
  const phaseRef = useRef<VoicePhase>("idle");

  // El proveedor de entrada decide el estado activo (live vs grabación iOS).
  const recognitionKind = useMemo(() => getRecognitionKind(), []);
  const activePhase: VoicePhase = recognitionKind === "recording" ? "recording" : "listening";

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  // Proveedor de salida (TTS): se configura una vez.
  useEffect(() => {
    const speech = getSpeechProvider();
    speechRef.current = speech;
    if (speech) {
      speech.onEnd = () => {
        if (!mountedRef.current) return;
        setPhase("idle");
      };
    }
    return () => {
      if (speech) speech.onEnd = null;
    };
  }, []);

  // Arranca al abrir: cancelar audio previo, desbloquear TTS y escuchar.
  useEffect(() => {
    if (!open) return;
    mountedRef.current = true;
    lastCountRef.current = messages.length;

    const speech = getSpeechProvider();
    speechRef.current = speech;
    speech?.cancel();
    // iOS exige que la primera emisión de audio ocurra dentro de un gesto.
    // El gesto real ya desbloqueó en el botón (unlockSpeech); este warm-up es
    // refuerzo por si el overlay se abre desde otro camino. El re-desbloqueo
    // tras la grabación del micrófono ocurre en cada toque del overlay.
    speech?.warmUp();

    const rec = getRecognitionProvider();
    recRef.current = rec;
    if (!rec) {
      setPhase("unsupported");
      return;
    }
    rec.onResult = handleResult;
    rec.onPartial = handlePartial;
    rec.onError = handleRecError;
    startListening();
    return () => {
      mountedRef.current = false;
      rec?.cancel();
      recRef.current = null;
      if (rec) {
        rec.onResult = null;
        rec.onPartial = null;
        rec.onError = null;
      }
      speech?.cancel();
      // A12 — abortar la petición del backend si hay una en curso.
      abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Autoscroll al fondo de la conversación.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking, open]);

  function handleResult(transcript: string) {
    if (!mountedRef.current) return;
    setLiveText("");
    setPhase("thinking");
    void send(transcript);
  }

  function handlePartial(text: string) {
    if (!mountedRef.current) return;
    setLiveText(text);
  }

  function handleRecError(code: RecognitionErrorCode, message?: string) {
    if (!mountedRef.current) return;
    switch (code) {
      case "timeout": {
        // Silencio: vuelve a escuchar (solo si nada lo reemplazó).
        window.setTimeout(() => {
          if (mountedRef.current && recRef.current && phaseRef.current === activePhase) {
            startListening();
          }
        }, 600);
        break;
      }
      case "unsupported":
        setPhase("unsupported");
        break;
      default:
        setMicErrorCode(code);
        setMicErrorMessage(message ?? null);
        setPhase("micError");
        break;
    }
  }

  function startListening() {
    if (!mountedRef.current) return;
    const rec = recRef.current;
    if (!rec) {
      setPhase("unsupported");
      return;
    }
    setMicErrorCode(null);
    setMicErrorMessage(null);
    setLiveText("");
    setPhase(activePhase);
    rec.start();
  }

  // Re-escucha manual: corta la voz (si Navi está hablando) y vuelve a oír.
  function relisten() {
    if (phase === "thinking" || !mountedRef.current) return;
    speechRef.current?.cancel();
    setMicErrorCode(null);
    setMicErrorMessage(null);
    setLiveText("");
    setPhase(activePhase);
    // Retardo breve: el browser libera el micrófono tras hablar.
    window.setTimeout(startListening, 250);
  }

  // La respuesta del backend llega como nuevo mensaje del asistente.
  useEffect(() => {
    if (phase !== "thinking" || messages.length <= lastCountRef.current) return;
    lastCountRef.current = messages.length;
    const last = messages[messages.length - 1];
    if (last?.role !== "assistant") return;

    const speech = speechRef.current;
    if (!speech || !speech.isSupported()) {
      setPhase("idle");
      return;
    }
    setPhase("speaking");
    speech.speak(last.text);
  }, [messages, phase]);

  const listening = phase === "listening" || phase === "recording";
  const micDenied = micErrorCode === "permission";
  const transcriptionFailed = micErrorCode === "network";

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
            className="absolute right-5 top-5 z-10 flex h-11 w-11 items-center justify-center rounded-full border border-glass-border bg-glass-surface/80 text-on-surface transition-colors hover:bg-surface-container-high active:scale-95"
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
              <NaviAvatar size={180} thinking={phase === "thinking"} />
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

          {/* Aviso legal: Navi no es asesor financiero */}
          <div className="shrink-0 px-6 pb-6 text-center">
            <p className="text-xs leading-snug text-on-surface-variant">{t("assistant.disclaimer")}</p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
