import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { Mic, X } from "lucide-react";

import { useAssistant } from "@/hooks/use-assistant";
import { NaviAvatar } from "@/features/assistant/navi-avatar";
import { cn } from "@/lib/utils";

type VoicePhase = "listening" | "thinking" | "speaking" | "idle" | "unsupported";

interface SpeechRecognitionResultLike {
  0: { transcript: string };
  isFinal: boolean;
}

interface SpeechRecognitionEventLike {
  results: { [index: number]: SpeechRecognitionResultLike } & { length: number };
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  abort: () => void;
}

interface SpeechRecognitionConstructorLike {
  new (): SpeechRecognitionLike;
}

const getSpeechRecognition = (): SpeechRecognitionConstructorLike | null => {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionConstructorLike;
    webkitSpeechRecognition?: SpeechRecognitionConstructorLike;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
};

interface NaviVoiceProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Interfaz de voz con "Navi": overlay a pantalla completa con el fondo
 * desenfocado, la bolita de Navi en grande y la conversación visible en
 * burbujas (Web Speech API: escucha → envía al backend → lee la respuesta).
 *
 * El historial se mantiene mientras la app está abierta: si Navi hace una
 * pregunta (cuenta, monto, motivo…), su texto queda en pantalla hasta que
 * el usuario responde por voz.
 *
 * Se abre manteniendo presionado el botón "+" del navbar.
 */
export function NaviVoice({ open, onClose }: NaviVoiceProps) {
  const { t } = useTranslation();
  const { messages, thinking, send } = useAssistant();
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const listRef = useRef<HTMLDivElement>(null);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const mountedRef = useRef(false);
  const transcriptRef = useRef("");
  const lastCountRef = useRef(0);
  const phaseRef = useRef<VoicePhase>("idle");

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  // Arranca al abrir: cancelar audio previo y escuchar.
  useEffect(() => {
    if (!open) return;
    mountedRef.current = true;
    lastCountRef.current = messages.length;
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();

    const SR = getSpeechRecognition();
    if (!SR) {
      setPhase("unsupported");
      return;
    }
    setPhase("listening");
    startListening();
    return () => {
      mountedRef.current = false;
      recRef.current?.abort();
      recRef.current = null;
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Autoscroll al fondo de la conversación.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking, open]);

  function startListening() {
    if (!mountedRef.current) return;
    // Nunca dejar una instancia activa: el browser solo permite una escucha.
    if (recRef.current) {
      recRef.current.abort();
      recRef.current = null;
    }
    const SR = getSpeechRecognition();
    if (!SR) {
      setPhase("unsupported");
      return;
    }
    const rec = new SR();
    recRef.current = rec;
    rec.lang = "es-ES";
    rec.continuous = false;
    rec.interimResults = false;

    rec.onresult = (e: SpeechRecognitionEventLike) => {
      const transcript = e.results[0]?.[0]?.transcript?.trim() ?? "";
      if (transcript) transcriptRef.current = transcript;
    };

    rec.onerror = () => {
      if (!mountedRef.current) return;
      if (recRef.current === rec) recRef.current = null;
      setPhase("idle");
    };

    rec.onend = () => {
      if (!mountedRef.current) return;
      if (recRef.current === rec) recRef.current = null;
      const transcript = transcriptRef.current;
      transcriptRef.current = "";
      if (transcript) {

        setPhase("thinking");
        void send(transcript);
      } else {
        // Silencio: vuelve a escuchar (solo si nada lo reemplazó).
        window.setTimeout(() => {
          if (mountedRef.current && recRef.current === null && phaseRef.current === "listening") {
            startListening();
          }
        }, 600);
      }
    };

    try {
      rec.start();
    } catch {
      // Chrome puede negarse justo después de hablar (audio sin liberar).
      recRef.current = null;
      window.setTimeout(() => {
        if (mountedRef.current && phaseRef.current === "listening") startListening();
      }, 400);
    }
  }

  // Re-escucha manual: corta la voz (si Navi está hablando) y vuelve a oír.
  function relisten() {
    if (phase === "thinking" || !mountedRef.current) return;
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();

    setPhase("listening");
    // Retardo breve: el browser libera el micrófono tras hablar.
    window.setTimeout(startListening, 250);
  }

  // La respuesta del backend llega como nuevo mensaje del asistente.
  useEffect(() => {
    if (phase !== "thinking" || messages.length <= lastCountRef.current) return;
    lastCountRef.current = messages.length;
    const last = messages[messages.length - 1];
    if (last?.role !== "assistant") return;
    setPhase("speaking");
    if (!("speechSynthesis" in window)) {
      setPhase("idle");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(last.text);
    utterance.lang = "es-ES";
    utterance.rate = 1.05;
    const esVoice = window.speechSynthesis
      .getVoices()
      .find((v) => v.lang?.toLowerCase().startsWith("es"));
    if (esVoice) utterance.voice = esVoice;
    utterance.onend = () => {
      if (!mountedRef.current) return;
      setPhase("idle");
    };
    utterance.onerror = () => {
      if (!mountedRef.current) return;
      setPhase("idle");
    };
    window.speechSynthesis.speak(utterance);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, phase]);

  const listening = phase === "listening";

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
              className="relative rounded-full focus-visible:outline-none"
              style={{ touchAction: "none" }}
            >
              <NaviAvatar size={180} thinking={phase === "thinking"} />
            </button>
          </motion.div>

          {/* Estado */}
          <div className="flex shrink-0 flex-col items-center gap-2 pb-12 pt-5">
            {phase === "unsupported" ? (
              <p className="text-sm text-on-surface-variant">
                {t("assistant.voice.unsupported")}
              </p>
            ) : (
              <p className="text-sm text-on-surface-variant">
                {listening
                  ? t("assistant.voice.listening")
                  : phase === "thinking"
                    ? t("assistant.voice.thinking")
                    : phase === "speaking"
                      ? t("assistant.voice.speaking")
                      : t("assistant.voice.talkAgain")}
              </p>
            )}
            {phase === "idle" && (
              <button
                type="button"
                aria-label={t("assistant.voice.talkAgain")}
                onClick={relisten}
                className="mt-2 flex h-11 w-11 items-center justify-center rounded-full bg-primary text-on-primary shadow-sm transition-all hover:opacity-90 active:scale-90"
              >
                <Mic className="h-5 w-5" />
              </button>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}