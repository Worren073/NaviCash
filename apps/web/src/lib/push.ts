/**
 * push — Suscripción y estado de Web Push del navegador.
 *
 * Flujo: el usuario pulsa "Activar" en Perfil (gesto requerido por iOS) →
 * pedimos permiso → leemos la clave VAPID del backend → pushManager.subscribe
 * → registramos el endpoint en la API. La entrega real la dispara el tick
 * horario (backend); la visualización vive en /sw-push.js.
 */

import { api } from "@/lib/api";
import { isIOSDevice } from "@/hooks/use-device-os";

export type PushState =
  | "on" // suscrito
  | "off" // soportado, aún sin suscribir
  | "denied" // permiso bloqueado por el usuario/sistema
  | "needs-install" // iOS: exige PWA instalada en el home
  | "unsupported"; // sin serviceWorker/PushManager

interface PushSubscriptionJSON {
  endpoint?: string | null;
  keys?: { p256dh?: string; auth?: string };
}

function base64UrlToUint8Array(base64Url: string): Uint8Array {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

/** Soporte bruto de APIs (sin considerar instalación en iOS). */
export function isPushCapable(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window
  );
}

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  const nav = navigator as Navigator & { standalone?: boolean };
  return (
    nav.standalone === true ||
    window.matchMedia("(display-mode: standalone)").matches ||
    window.matchMedia("(display-mode: fullscreen)").matches
  );
}

/** Estado actual para pintar la UI de Perfil. */
export async function getPushState(): Promise<PushState> {
  if (!isPushCapable()) return "unsupported";
  // iOS solo expone Push a las PWAs instaladas desde el home (Safari).
  if (isIOSDevice() && !isStandalone()) return "needs-install";
  if ("Notification" in window && Notification.permission === "denied") {
    return "denied";
  }
  const registration = await navigator.serviceWorker.getRegistration();
  const existing = await registration?.pushManager.getSubscription();
  return existing ? "on" : "off";
}

/**
 * Pide permiso, suscribe y registra el endpoint en el backend.
 * Lanza Error con mensaje técnico; la UI traduce según el PushState previo.
 */
export async function subscribeToPush(): Promise<void> {
  if (!isPushCapable()) throw new Error("push_unsupported");
  if ("Notification" in window && Notification.permission === "denied") {
    throw new Error("push_denied");
  }
  const { publicKey } = await api.get<{ publicKey: string }>("/push/vapid-key");
  const registration =
    (await navigator.serviceWorker.getRegistration()) ??
    (await navigator.serviceWorker.ready);
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: base64UrlToUint8Array(publicKey) as BufferSource,
  });
  const json = subscription.toJSON() as PushSubscriptionJSON;
  await api.post("/push/subscriptions", {
    endpoint: json.endpoint,
    keys: json.keys,
  });
}

/** Cancela la suscripción local y la baja del backend (best-effort). */
export async function unsubscribeFromPush(): Promise<void> {
  const registration = await navigator.serviceWorker.getRegistration();
  const subscription = await registration?.pushManager.getSubscription();
  if (!subscription) return;
  const endpoint = subscription.endpoint;
  await subscription.unsubscribe();
  try {
    await api.delete(`/push/subscriptions?endpoint=${encodeURIComponent(endpoint)}`);
  } catch {
    // Si ya no existe en el backend (poda 410), igualmente quedó cancelada.
  }
}
