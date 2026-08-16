/**
 * Proveedor de reconocimiento de voz (STT) para iOS.
 *
 * iOS Safari no expone la Web Speech API de reconocimiento, pero sí
 * ``getUserMedia`` + ``MediaRecorder`` (desde iOS 14.5). Este proveedor:
 *
 * 1. Pide el micrófono y graba con ``MediaRecorder`` (audio/mp4 o webm).
 * 2. Detecta el corte por silencio con VAD simple (RMS sobre el dominio del
 *    tiempo vía ``AnalyserNode``): arranca a capturar tras el primer habla y
 *    se detiene tras ``SILENCE_MS`` de silencio (o el tope de ``MAX_DURATION``).
 * 3. Sube el clip a ``POST /api/assistant/transcribe`` y entrega el transcript
 *    por ``onResult``.
 */

import { api } from "@/lib/api";
import type { RecognitionErrorCode, RecognitionProvider } from "./types";

const MAX_DURATION_MS = 30_000;
const NO_SPEECH_TIMEOUT_MS = 8_000;
const SILENCE_MS = 1_400;
const RMS_THRESHOLD = 0.01;
const TRANSCRIBE_TIMEOUT_MS = 30_000;

interface MediaRecorderLike {
  state: "inactive" | "recording" | "paused";
  mimeType: string;
  start(): void;
  stop(): void;
  ondataavailable: ((e: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
  onerror: (() => void) | null;
}

interface MediaRecorderConstructorLike {
  new (stream: MediaStream, options?: { mimeType?: string }): MediaRecorderLike;
  isTypeSupported(mimeType: string): boolean;
}

export class MediaRecorderRecognitionProvider implements RecognitionProvider {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorderLike | null = null;
  private audioContext: AudioContext | null = null;
  private rafId = 0;
  private chunks: Blob[] = [];
  private speaking = false;
  private silenceStart = 0;
  private startedAt = 0;
  private finalized = false;
  private aborting = false;
  onResult: ((transcript: string) => void) | null = null;
  onError: ((code: RecognitionErrorCode) => void) | null = null;

  isSupported(): boolean {
    if (typeof window === "undefined") return false;
    return (
      typeof window.MediaRecorder === "function" &&
      typeof window.AudioContext === "function" &&
      navigator.mediaDevices?.getUserMedia != null
    );
  }

  start(): void {
    if (this.finalized) this.reset();
    this.aborting = false;
    this.chunks = [];
    this.speaking = false;
    this.silenceStart = 0;

    navigator.mediaDevices
      .getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      .then((stream) => {
        if (this.aborting) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        this.stream = stream;
        this.startRecorder(stream);
        this.startVAD(stream);
      })
      .catch((err) => {
        const code: RecognitionErrorCode =
          err instanceof DOMException && err.name === "NotAllowedError" ? "permission" : "error";
        this.onError?.(code);
      });
  }

  stop(): void {
    this.finalize();
  }

  cancel(): void {
    this.aborting = true;
    this.finalize();
  }

  private startRecorder(stream: MediaStream): void {
    const MR = window.MediaRecorder as unknown as MediaRecorderConstructorLike;
    const mimeType = MR.isTypeSupported("audio/mp4") ? "audio/mp4" : "audio/webm";
    const recorder = new MR(stream, { mimeType });
    this.recorder = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) this.chunks.push(e.data);
    };

    recorder.onerror = () => {
      if (this.finalized) return;
      this.release();
      this.onError?.("error");
    };

    recorder.onstop = () => {
      const blob = new Blob(this.chunks, { type: recorder.mimeType || mimeType });
      if (this.aborting) {
        this.release();
        return;
      }
      if (this.chunks.length === 0) {
        // Nunca se capturó habla: sin subida, el overlay reintenta escuchar.
        this.release();
        this.onError?.("timeout");
        return;
      }
      void this.upload(blob);
    };

    recorder.start();
    this.startedAt = Date.now();
  }

  private startVAD(stream: MediaStream): void {
    const ctx = new AudioContext();
    this.audioContext = ctx;
    // iOS: asegurar que el contexto corre dentro del gesto que abrió el mic.
    if (ctx.state === "suspended") void ctx.resume();

    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.3;
    ctx.createMediaStreamSource(stream).connect(analyser);

    const buffer = new Float32Array(analyser.fftSize);
    const loop = () => {
      if (this.finalized || this.aborting) return;
      analyser.getFloatTimeDomainData(buffer);

      let sum = 0;
      for (let i = 0; i < buffer.length; i++) sum += buffer[i] * buffer[i];
      const rms = Math.sqrt(sum / buffer.length);

      if (rms > RMS_THRESHOLD) {
        if (!this.speaking) {
          this.speaking = true;
          this.silenceStart = 0;
        }
      } else if (this.speaking) {
        if (this.silenceStart === 0) {
          this.silenceStart = Date.now();
        } else if (Date.now() - this.silenceStart >= SILENCE_MS) {
          this.finalize();
          return;
        }
      }

      if (!this.speaking && Date.now() - this.startedAt >= NO_SPEECH_TIMEOUT_MS) {
        // Silencio desde el inicio: detener sin subir y dejar que se reintente.
        this.finalize();
        return;
      }

      if (Date.now() - this.startedAt >= MAX_DURATION_MS) {
        this.finalize();
        return;
      }
      this.rafId = requestAnimationFrame(loop);
    };
    this.rafId = requestAnimationFrame(loop);
  }

  private finalize(): void {
    if (this.finalized) return;
    this.finalized = true;
    if (this.rafId) cancelAnimationFrame(this.rafId);
    if (this.audioContext) {
      this.audioContext.close().catch(() => undefined);
      this.audioContext = null;
    }
    if (this.recorder && this.recorder.state === "recording") {
      try {
        this.recorder.stop();
      } catch {
        /* ya detenido */
      }
    } else {
      this.release();
    }
  }

  private async upload(blob: Blob): Promise<void> {
    const form = new FormData();
    form.append("audio", blob, "navi-voice.mp4");
    try {
      const { transcript } = await api.post<{ transcript: string }>(
        "/assistant/transcribe",
        form,
        { signal: AbortSignal.timeout(TRANSCRIBE_TIMEOUT_MS) },
      );
      const trimmed = (transcript ?? "").trim();
      this.release();
      if (trimmed) {
        this.onResult?.(trimmed);
      } else {
        this.onError?.("timeout");
      }
    } catch {
      this.release();
      this.onError?.("network");
    }
  }

  private release(): void {
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    this.recorder = null;
    this.chunks = [];
  }

  private reset(): void {
    this.finalized = false;
    this.aborting = false;
    this.stream = null;
    this.recorder = null;
    this.audioContext = null;
    this.chunks = [];
    this.speaking = false;
    this.silenceStart = 0;
    this.startedAt = 0;
  }
}
