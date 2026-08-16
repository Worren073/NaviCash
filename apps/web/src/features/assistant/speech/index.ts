/**
 * Fábrica de proveedores de voz de Navi.
 *
 * - Salida (TTS): ``speechSynthesis`` nativo, disponible en todos los
 *   navegadores (incluido iOS).
 * - Entrada (STT): Web Speech API en Android/desktop; en iOS se graba con
 *   ``MediaRecorder`` y se transcribe en el backend (Whisper).
 *
 * Las instancias se cachean a nivel de módulo: el proveedor de síntesis
 * recarga las voces en ``voiceschanged`` y no conviene recrearlo.
 */

import { isIOSDevice } from "@/hooks/use-device-os";

import { MediaRecorderRecognitionProvider } from "./media-recorder-recognition";
import type { RecognitionProvider, SpeechProvider } from "./types";
import { WebSpeechRecognitionProvider } from "./web-speech-recognition";
import { WebSpeechSynthesisProvider } from "./web-speech-synthesis";

let cachedSpeech: SpeechProvider | null | undefined;
let cachedRecognition: RecognitionProvider | null | undefined;

export function getSpeechProvider(): SpeechProvider | null {
  if (cachedSpeech !== undefined) return cachedSpeech;
  cachedSpeech =
    typeof window !== "undefined" && "speechSynthesis" in window
      ? new WebSpeechSynthesisProvider()
      : null;
  return cachedSpeech;
}

export function getRecognitionProvider(): RecognitionProvider | null {
  if (cachedRecognition !== undefined) return cachedRecognition;
  if (typeof window === "undefined") {
    cachedRecognition = null;
    return null;
  }
  const provider: RecognitionProvider | null = isIOSDevice()
    ? new MediaRecorderRecognitionProvider()
    : new WebSpeechRecognitionProvider();
  cachedRecognition = provider.isSupported() ? provider : null;
  return cachedRecognition;
}

/**
 * Cómo captura la voz este dispositivo: "live" (Web Speech, corte automático
 * del navegador) o "recording" (iOS: grabación con corte por silencio).
 * ``null`` si no hay ningún método de entrada.
 */
export function getRecognitionKind(): "live" | "recording" | null {
  if (getRecognitionProvider() === null) return null;
  return isIOSDevice() ? "recording" : "live";
}
