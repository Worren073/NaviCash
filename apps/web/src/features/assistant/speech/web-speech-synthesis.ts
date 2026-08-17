/**
 * Proveedor de síntesis de voz (TTS) basado en ``speechSynthesis``.
 *
 * Funciona en todos los navegadores que exponen la Web Speech API (incluido
 * iOS Safari). Incluye los arreglos específicos de iOS:
 * - ``getVoices()`` llega vacío hasta que el usuario interactúa y dispara
 *   ``voiceschanged``: las voces se recargan en ese evento y de nuevo en cada
 *   ``speak()`` (en iOS pueden llegar tarde a la primera respuesta).
 * - El audio solo se "desbloquea" dentro de un gesto del usuario: ``warmUp()``
 *   emite un utterance casi silencioso desde el gesto (tap/pointer) que abre
 *   el overlay. No se cancela de inmediato (eso anularía el desbloqueo).
 * - El micrófono (MediaRecorder) vuelve a bloquear el audio session de iOS:
 *   por eso el overlay re-ejecuta ``warmUp()`` en cada toque del usuario.
 * - ``onend`` no siempre se dispara en iOS: se usa un timer de respaldo
 *   calculado a partir de la longitud del texto.
 */

import type { SpeechProvider } from "./types";

export class WebSpeechSynthesisProvider implements SpeechProvider {
  private voices: SpeechSynthesisVoice[] = [];
  private endTimer: number | null = null;
  private unlockCtx: AudioContext | null = null;
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
    // Desbloquear el audio session de iOS sin tocar speechSynthesis. Cuando
    // speak() se invoca desde un useEffect (fuera de un gesto del usuario),
    // iOS puede silenciar la emisión; reanudar un AudioContext mantiene viva
    // la sesión de audio. Se usa AudioContext en vez de warmUp() porque este
    // último llama synth.cancel() con un timer que mataría el utterance real.
    this._unlockAudio();
    const synth = window.speechSynthesis;
    synth.cancel();
    this.clearTimer();

    // En iOS las voces llegan tarde (voiceschanged): recargar justo antes de
    // hablar garantiza elegir una voz en español en la primera respuesta.
    this.loadVoices();

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
      // Volume 0.01 (no 0: algunos iOS ignoran el mute y 0 anula la emisión).
      // NO se cancela de inmediato: iOS necesita que la utterance llegue a
      // emitirse para desbloquear el audio session; se corta un instante
      // después como limpieza.
      const silent = new SpeechSynthesisUtterance(" ");
      silent.volume = 0.01;
      silent.rate = 1;
      synth.speak(silent);
      window.setTimeout(() => synth.cancel(), 150);
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

  /**
   * Mantiene viva la sesión de audio de iOS reanudando un AudioContext.
   * A diferencia de ``warmUp()``, NO toca ``speechSynthesis`` (sin
   * ``cancel()`` ni utterances), por lo que es seguro llamarlo justo antes
   * de ``speak()`` sin riesgo de matar el utterance que se va a cola.
   */
  private _unlockAudio(): void {
    try {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Ctor) return;
      this.unlockCtx = this.unlockCtx ?? new Ctor();
      if (this.unlockCtx.state === "suspended") void this.unlockCtx.resume();
    } catch {
      /* best effort: desbloqueo del audio session iOS */
    }
  }
}
