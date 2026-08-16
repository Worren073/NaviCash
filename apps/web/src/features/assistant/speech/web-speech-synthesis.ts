/**
 * Proveedor de síntesis de voz (TTS) basado en ``speechSynthesis``.
 *
 * Funciona en todos los navegadores que exponen la Web Speech API (incluido
 * iOS Safari). Incluye los arreglos específicos de iOS:
 * - ``getVoices()`` llega vacío hasta que el usuario interactúa y dispara
 *   ``voiceschanged``: las voces se recargan en ese evento.
 * - El audio solo se "desbloquea" dentro de un gesto del usuario: ``warmUp()``
 *   emite un utterance en silencio desde el tap que abre el overlay.
 * - ``onend`` no siempre se dispara en iOS: se usa un timer de respaldo
 *   calculado a partir de la longitud del texto.
 */

import type { SpeechProvider } from "./types";

export class WebSpeechSynthesisProvider implements SpeechProvider {
  private voices: SpeechSynthesisVoice[] = [];
  private endTimer: number | null = null;
  onEnd: (() => void) | null = null;

  constructor() {
    if (typeof window === "undefined") return;
    this.loadVoices();
    window.speechSynthesis?.addEventListener("voiceschanged", () => this.loadVoices());
  }

  isSupported(): boolean {
    return typeof window !== "undefined" && "speechSynthesis" in window;
  }

  speak(text: string): void {
    if (!this.isSupported() || !text) return;
    const synth = window.speechSynthesis;
    synth.cancel();
    this.clearTimer();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "es-ES";
    utterance.rate = 1.05;
    const voice = this.voices.find((v) => v.lang?.toLowerCase().startsWith("es"));
    if (voice) utterance.voice = voice;

    const finish = () => this.emitEnd();
    utterance.onend = finish;
    utterance.onerror = finish;
    // Respaldo iOS: onend puede no dispararse → estimar por longitud del texto.
    const estimated = Math.min(Math.max(text.length * 90, 4000), 60000);
    this.endTimer = window.setTimeout(finish, estimated);

    synth.speak(utterance);
  }

  cancel(): void {
    this.clearTimer();
    if (!this.isSupported()) return;
    window.speechSynthesis.cancel();
  }

  warmUp(): void {
    if (!this.isSupported()) return;
    const synth = window.speechSynthesis;
    synth.cancel();
    try {
      const silent = new SpeechSynthesisUtterance(" ");
      silent.volume = 0;
      synth.speak(silent);
      synth.cancel();
    } catch {
      /* best effort: desbloqueo del audio session iOS */
    }
  }

  private loadVoices(): void {
    if (!this.isSupported()) return;
    this.voices = window.speechSynthesis.getVoices();
  }

  private clearTimer(): void {
    if (this.endTimer !== null) {
      window.clearTimeout(this.endTimer);
      this.endTimer = null;
    }
  }

  private emitEnd(): void {
    this.clearTimer();
    this.onEnd?.();
  }
}
