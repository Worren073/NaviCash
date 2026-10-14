import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAssistant } from "@/hooks/use-assistant";
import { isIOSDevice } from "@/hooks/use-device-os";
import {
  getRecognitionKind,
  getRecognitionProvider,
  getSpeechProvider,
} from "@/features/assistant/speech";
import type { RecognitionErrorCode } from "@/features/assistant/speech/types";

export type VoicePhase =
  | "listening"
  | "recording"
  | "thinking"
  | "speaking"
  | "idle"
  | "unsupported"
  | "micError";

interface UseNaviVoiceOptions {
  /** Sesión de voz activa: al pasar a `true` arranca la escucha y el TTS. */
  active: boolean;
  /**
   * Volver a escuchar automáticamente tras un silencio prolongado (overlay a
   * pantalla completa). En modo push-to-talk (mini) se deja en `false`: soltar
   * finaliza la captura y no se re-escucha.
   */
  relistenOnTimeout?: boolean;
}

/**
 * Sesión de voz de "Navi" compartida por el overlay a pantalla completa
 * (`navi-voice.tsx`) y el modo compacto anclado a la burbuja
 * (`navi-voice-inline.tsx`).
 *
 * Encapsula la máquina de estados de la conversación hablada:
 * entrada (Web Speech en Android/desktop; MediaRecorder + VAD en iOS),
 * envío al backend a través de `useAssistant` y salida por TTS
 * (`speechSynthesis`), con el re-desbloqueo de la sesión de audio de iOS.
 */
export function useNaviVoice({ active, relistenOnTimeout = true }: UseNaviVoiceOptions) {
  const { messages, thinking, send, abort } = useAssistant();
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [micErrorCode, setMicErrorCode] = useState<RecognitionErrorCode | null>(null);
  const [micErrorMessage, setMicErrorMessage] = useState<string | null>(null);
  const [liveText, setLiveText] = useState("");

  const mountedRef = useRef(false);
  const lastCountRef = useRef(0);
  const phaseRef = useRef<VoicePhase>("idle");
  const recRef = useRef<ReturnType<typeof getRecognitionProvider>>(null);
  const speechRef = useRef<ReturnType<typeof getSpeechProvider>>(null);
  // Callbacks estables para los proveedores (evitan closures obsoletos).
  const sendRef = useRef(send);
  const relistenRef = useRef(relistenOnTimeout);
  sendRef.current = send;
  relistenRef.current = relistenOnTimeout;

  // El proveedor de entrada decide el estado activo (live vs grabación iOS).
  const recognitionKind = useMemo(() => getRecognitionKind(), []);
  const activePhase: VoicePhase = recognitionKind === "recording" ? "recording" : "listening";
  // En iOS el interruptor de silencio silencia speechSynthesis (sin API para
  // forzarlo): el overlay muestra un recordatorio persistente.
  const isIOS = isIOSDevice();

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

  const startListening = useCallback(() => {
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
  }, [activePhase]);

  const handleResult = useCallback((transcript: string) => {
    if (!mountedRef.current) return;
    setLiveText("");
    setPhase("thinking");
    void sendRef.current(transcript);
  }, []);

  const handlePartial = useCallback((text: string) => {
    if (!mountedRef.current) return;
    setLiveText(text);
  }, []);

  const handleRecError = useCallback(
    (code: RecognitionErrorCode, message?: string) => {
      if (!mountedRef.current) return;
      switch (code) {
        case "timeout": {
          // Silencio: si el modo permite re-escuchar, vuelve a hacerlo.
          if (!relistenRef.current) {
            setPhase("idle");
            return;
          }
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
    },
    [activePhase, startListening],
  );

  // Arranca al activar: cancelar audio previo, desbloquear TTS y escuchar.
  useEffect(() => {
    if (!active) return;
    mountedRef.current = true;
    lastCountRef.current = messages.length;

    const speech = getSpeechProvider();
    speechRef.current = speech;
    speech?.cancel();
    // iOS exige que la primera emisión de audio ocurra dentro de un gesto; el
    // gesto real (pointerdown) ya llamó a `unlockSpeech`; este warm-up refuerza.
    speech?.warmUp();

    const rec = getRecognitionProvider();
    recRef.current = rec;
    if (!rec) {
      setPhase("unsupported");
      return () => {
        mountedRef.current = false;
        speech?.cancel();
        abort();
      };
    }
    rec.onResult = handleResult;
    rec.onPartial = handlePartial;
    rec.onError = handleRecError;
    startListening();
    return () => {
      mountedRef.current = false;
      rec.cancel();
      recRef.current = null;
      rec.onResult = null;
      rec.onPartial = null;
      rec.onError = null;
      speech?.cancel();
      abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // La respuesta del backend llega como nuevo mensaje del asistente: se lee.
  useEffect(() => {
    if (!active) return;
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
  }, [messages, phase, active]);

  // Re-escucha manual: corta la voz (si Navi habla) y vuelve a oír.
  const relisten = useCallback(() => {
    if (phaseRef.current === "thinking" || !mountedRef.current) return;
    speechRef.current?.cancel();
    setMicErrorCode(null);
    setMicErrorMessage(null);
    setLiveText("");
    setPhase(activePhase);
    // Retardo breve: el navegador libera el micrófono tras hablar.
    window.setTimeout(startListening, 250);
  }, [activePhase, startListening]);

  /** Finaliza la captura en curso (push-to-talk: al soltar). */
  const stop = useCallback(() => {
    recRef.current?.stop();
  }, []);

  /** Aborta la captura sin resultado y corta el TTS. */
  const cancel = useCallback(() => {
    recRef.current?.cancel();
    speechRef.current?.cancel();
  }, []);

  const listening = phase === "listening" || phase === "recording";
  const micDenied = micErrorCode === "permission";
  const transcriptionFailed = micErrorCode === "network";

  return {
    messages,
    thinking,
    phase,
    liveText,
    micErrorCode,
    micErrorMessage,
    recognitionKind,
    isIOS,
    listening,
    micDenied,
    transcriptionFailed,
    start: startListening,
    stop,
    cancel,
    relisten,
  };
}
