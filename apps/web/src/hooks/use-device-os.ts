/**
 * useDeviceOS — Hook para detectar el sistema operativo del usuario.
 *
 * Detecta: iOS, Android, o Web (desktop)
 * También detecta si es PWA instalada o navegador
 */

import { useEffect, useState } from "react";

export type DeviceOS = "ios" | "android" | "web";
export type AppType = "pwa" | "web" | "unknown";

interface DeviceInfo {
  os: DeviceOS;
  appType: AppType;
  isStandalone: boolean;
  userAgent: string;
  supportsVoice: boolean;
  supportsNotifications: boolean;
}

/** Detecta iOS por UA (y iPad como desktop con pantalla táctil). */
export function isIOSDevice(): boolean {
  if (typeof navigator === "undefined") return false;
  const userAgent = navigator.userAgent.toLowerCase();
  return (
    /iphone|ipad|ipod|ios/.test(userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

export function useDeviceOS(): DeviceInfo {
  const [deviceInfo, setDeviceInfo] = useState<DeviceInfo>({
    os: "web",
    appType: "web",
    isStandalone: false,
    userAgent: "",
    supportsVoice: false,
    supportsNotifications: false,
  });

  useEffect(() => {
    const userAgent = navigator.userAgent.toLowerCase();

    // Detectar OS
    const isIOS = isIOSDevice();
    const isAndroid = /android|webos/.test(userAgent);
    const os: DeviceOS = isIOS ? "ios" : isAndroid ? "android" : "web";

    // Detectar si es PWA instalada
    const isStandalone =
      (window.navigator as { standalone?: boolean }).standalone === true ||
      window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: fullscreen)").matches;

    const appType: AppType = isStandalone ? "pwa" : "web";

    // Detectar soporte de APIs: la síntesis de voz (speechSynthesis) existe
    // también en iOS; la entrada por voz se resuelve por proveedor en el
    // asistente (Web Speech en Android/desktop, grabación+transcripción en iOS).
    const supportsVoice = "speechSynthesis" in window;
    const supportsNotifications = "Notification" in window;

    setDeviceInfo({
      os,
      appType,
      isStandalone,
      userAgent,
      supportsVoice,
      supportsNotifications,
    });
  }, []);

  return deviceInfo;
}

/**
 * Utility: Obtener nombre legible del SO
 */
export function getOSName(os: DeviceOS): string {
  const names: Record<DeviceOS, string> = {
    ios: "iOS",
    android: "Android",
    web: "Web",
  };
  return names[os];
}

/**
 * Utility: Obtener mensaje de limitaciones para iOS
 */
export function getIOSLimitations(): string[] {
  return [
    "El micrófono requiere permiso del navegador",
    "Acceso offline limitado",
    "Algunas características PWA pueden no funcionar completamente",
  ];
}
