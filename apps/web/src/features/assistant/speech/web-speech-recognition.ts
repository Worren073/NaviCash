/**
 * Proveedor de reconocimiento de voz (STT) basado en la Web Speech API.
 *
 * Se usa en Android y desktop (Chrome/Edge). En iOS esta API no existe; el
 * flujo iOS lo cubre ``MediaRecorderRecognitionProvider``.
 *
 * El silencio sin habla se reporta como ``onError("timeout")`` para que el
 * overlay vuelva a escuchar, replicando el comportamiento original del
 * componente ``NaviVoice``.
 */

import type { RecognitionErrorCode, RecognitionProvider } from "./types";

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
  onResult: ((transcript: string) => void) | null = null;
  onError: ((code: RecognitionErrorCode) => void) | null = null;

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
    rec.interimResults = false;

    rec.onresult = (e) => {
      const transcript = e.results[0]?.[0]?.transcript?.trim() ?? "";
      if (transcript) this.transcript = transcript;
    };

    rec.onerror = () => {
      if (this.rec !== rec) return;
      this.rec = null;
      this.onError?.("error");
    };

    rec.onend = () => {
      if (this.rec !== rec) return;
      this.rec = null;
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
  }
}
