/**
 * Tipos compartidos por los proveedores de voz de Navi.
 *
 * El overlay de voz usa dos proveedores desacoplados:
 * - ``SpeechProvider``: salida (TTS) con ``speechSynthesis`` nativo.
 * - ``RecognitionProvider``: entrada (STT) — Web Speech API en Android/desktop
 *   y MediaRecorder + transcripción por backend en iOS.
 */

export interface SpeechProvider {
  /** True si el navegador puede sintetizar voz. */
  isSupported(): boolean;
  /** Lee ``text`` en voz alta (es-ES). */
  speak(text: string): void;
  /** Detiene la voz en curso (si la hay). */
  cancel(): void;
  /**
   * Desbloquea el audio session del navegador (iOS exige que la primera
   * emisión ocurra dentro de un gesto del usuario). Llamar en el tap inicial.
   */
  warmUp(): void;
  /** Se dispara cuando termina de hablar (o falla). */
  onEnd: (() => void) | null;
}

export type RecognitionErrorCode =
  | "permission" // micrófono denegado o no disponible
  | "unsupported" // el dispositivo no ofrece ningún método de escucha
  | "network" // falló la transcripción por red/servidor
  | "timeout" // silencio prolongado sin capturar habla
  | "error"; // error genérico del proveedor

export interface RecognitionProvider {
  /** True si el dispositivo puede capturar voz (reconocimiento o grabación). */
  isSupported(): boolean;
  /** Empieza a escuchar/grabar. */
  start(): void;
  /** Termina la escucha y entrega el resultado (si lo hay). */
  stop(): void;
  /** Aborta sin resultado. */
  cancel(): void;
  /**
   * Texto provisional mientras se escucha (palabra por palabra). Solo los
   * proveedores con transcripción en tiempo real lo emiten (Web Speech);
   * iOS (grabación) entrega solo el resultado final por ``onResult``.
   */
  onPartial: ((text: string) => void) | null;
  /** Texto final capturado (transcript local o del backend). */
  onResult: ((transcript: string) => void) | null;
  /**
   * Error de captura/transcripción. ``message`` (opcional) porta el detalle
   * del servidor cuando está disponible, para mostrarlo al usuario.
   */
  onError: ((code: RecognitionErrorCode, message?: string) => void) | null;
}
