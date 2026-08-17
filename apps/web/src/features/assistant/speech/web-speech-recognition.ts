/**
 * Proveedor de reconocimiento de voz (STT) basado en la Web Speech API.
 *
 * Se usa en Android, desktop (Chrome/Edge) e iOS 14.5+ (donde el navegador
 * expone ``webkitSpeechRecognition``). En iOS, ``webkitSpeechRecognition``
 * retoma la sesión de audio del sistema; al terminar, la libera. Para que
 * ``speechSynthesis.speak()`` (llamado desde un ``useEffect``) pueda
 * reproducir audio después, este proveedor crea un AudioContext nuevo y lo
 * reanuda inmediatamente tras ``onend``/``onerror`` para re-activar la sesión.
 *
 * El silencio sin habla se reporta como ``onError("timeout")`` para que el
 * overlay vuelva a escuchar, replicando el comportamiento original del
 * componente ``NaviVoice``.
 */

import type { RecognitionErrorCode, RecognitionProvider } from "./types";

/** iOS: tiempo que el AudioContext de puente se mantiene abierto. */
const BRIDGE_MS = 500;

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
  stop: () => void;
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

// Chrome puede negarse a escuchar justo después de hablar (audio sin liberar):
// reintentos antes de rendirse.
const MAX_START_ATTEMPTS = 2;
const START_RETRY_MS = 400;

export class WebSpeechRecognitionProvider implements RecognitionProvider {
  private rec: SpeechRecognitionLike | null = null;
  private transcript = "";
  private startAttempts = 0;
  /** AudioContext de puente para mantener viva la sesión de audio en iOS. */
  private bridgeCtx: AudioContext | null = null;
  private bridgeTimer: ReturnType<typeof setTimeout> | null = null;
  onPartial: ((text: string) => void) | null = null;
  onResult: ((transcript: string) => void) | null = null;
  onError: ((code: RecognitionErrorCode, message?: string) => void) | null = null;

  isSupported(): boolean {
    return getSpeechRecognition() !== null;
  }

  start(): void {
    if (this.rec) {
      this.rec.abort();
      this.rec = null;
    }
    const SR = getSpeechRecognition();
    if (!SR) {
      this.onError?.("unsupported");
      return;
    }

    const rec = new SR();
    this.rec = rec;
    this.transcript = "";
    rec.lang = "es-ES";
    rec.continuous = false;
    // Resultados intermedios: mientras el usuario habla se emiten por
    // ``onPartial`` para pintar el texto palabra por palabra.
    rec.interimResults = true;

    rec.onresult = (e) => {
      const interim: string[] = [];
      for (let i = 0; i < e.results.length; i++) {
        const result = e.results[i];
        const text = result?.[0]?.transcript?.trim() ?? "";
        if (!text) continue;
        if (result.isFinal) {
          // Acumular el tramo definitivo; se entrega completo al terminar.
          this.transcript = [this.transcript, text].filter(Boolean).join(" ");
        } else {
          interim.push(text);
        }
      }
      const provisional = [this.transcript, ...interim].filter(Boolean).join(" ");
      if (provisional) this.onPartial?.(provisional);
    };

    rec.onerror = () => {
      if (this.rec !== rec) return;
      this.rec = null;
      // iOS: re-activar la sesión de audio para que el overlay pueda
      // volver a escuchar o hablar un mensaje de error.
      this._bridgeAudioSession();
      this.onError?.("error");
    };

    rec.onend = () => {
      if (this.rec !== rec) return;
      this.rec = null;
      // iOS: webkitSpeechRecognition libera la sesión de audio al terminar.
      // Re-activarla con un AudioContext nuevo para que speechSynthesis
      // (llamado desde un useEffect tras la respuesta del backend) pueda
      // reproducir audio.  Esto replica el patrón de MediaRecorder con su
      // AudioContext.close() diferido.
      this._bridgeAudioSession();
      const transcript = this.transcript;
      this.transcript = "";
      if (transcript) {
        this.onResult?.(transcript);
      } else {
        // Silencio: el overlay decide si vuelve a escuchar.
        this.onError?.("timeout");
      }
    };

    try {
      rec.start();
      this.startAttempts = 0;
    } catch {
      this.rec = null;
      if (this.startAttempts < MAX_START_ATTEMPTS) {
        this.startAttempts += 1;
        window.setTimeout(() => this.start(), START_RETRY_MS);
      } else {
        this.onError?.("error");
      }
    }
  }

  stop(): void {
    if (this.rec) this.rec.stop();
  }

  cancel(): void {
    this.rec?.abort();
    this.rec = null;
    this._clearBridge();
  }

  /**
   * Crea un AudioContext nuevo y lo reanuda para re-activar la sesión de
   * audio de iOS después de que ``webkitSpeechRecognition`` la liberó.
   * Se cierra tras ``BRIDGE_MS`` para liberar recursos.  Si en ese
   * intervalo ``speechSynthesis.speak()`` se invocó, la sesión de audio
   * ya quedó tomada por la utterance y el cierre no la afecta.
   */
  private _bridgeAudioSession(): void {
    try {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Ctor) return;
      // Un AudioContext en estado "running" no re-activa la sesión iOS
      // con solo resume(); se necesita uno nuevo.
      this._clearBridge();
      const ctx = new Ctor();
      this.bridgeCtx = ctx;
      if (ctx.state === "suspended") void ctx.resume();
      this.bridgeTimer = window.setTimeout(() => {
        ctx.close().catch(() => undefined);
        this.bridgeCtx = null;
        this.bridgeTimer = null;
      }, BRIDGE_MS);
    } catch {
      /* best effort: puente de sesión de audio iOS */
    }
  }

  private _clearBridge(): void {
    if (this.bridgeTimer !== null) {
      clearTimeout(this.bridgeTimer);
      this.bridgeTimer = null;
    }
    if (this.bridgeCtx) {
      this.bridgeCtx.close().catch(() => undefined);
      this.bridgeCtx = null;
    }
  }
}
