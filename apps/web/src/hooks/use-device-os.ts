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
    const isIOS = /iphone|ipad|ipod|ios/.test(userAgent) || 
                  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    const isAndroid = /android|webos/.test(userAgent);
    const os: DeviceOS = isIOS ? "ios" : isAndroid ? "android" : "web";

    // Detectar si es PWA instalada
    const isStandalone = 
      (window.navigator as any).standalone === true ||
      window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: fullscreen)").matches;
    
    const appType: AppType = isStandalone ? "pwa" : "web";

    // Detectar soporte de APIs
    const supportsVoice = "speechSynthesis" in window && !isIOS;
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
    "Voz de Navi no disponible en iOS (limitación de Safari)",
    "Burbuja de chat puede verse cuadrada",
    "Acceso offline limitado",
    "Algunas características PWA pueden no funcionar completamente",
  ];
}
