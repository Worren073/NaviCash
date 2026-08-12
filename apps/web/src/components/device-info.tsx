/**
 * DeviceInfo — Componente de debug para mostrar info del dispositivo
 * Útil en development para verificar detección de OS
 */

import { useDeviceOS, getOSName } from "@/hooks/use-device-os";
import { Smartphone } from "lucide-react";

export function DeviceInfo() {
  const device = useDeviceOS();

  // Solo mostrar en desarrollo
  if (import.meta.env.MODE !== "development") {
    return null;
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 p-3 rounded-lg bg-surface-container border border-glass-border text-xs font-mono text-on-surface max-w-xs shadow-lg">
      <div className="flex items-center gap-2 mb-2 font-semibold">
        <Smartphone className="h-4 w-4" />
        Device Info
      </div>
      <div className="space-y-1 text-on-surface-variant">
        <div>
          <span className="text-on-surface">OS:</span> {getOSName(device.os)}
        </div>
        <div>
          <span className="text-on-surface">App:</span> {device.appType}
        </div>
        <div>
          <span className="text-on-surface">Standalone:</span> {device.isStandalone ? "✓" : "✗"}
        </div>
        <div>
          <span className="text-on-surface">Voice:</span> {device.supportsVoice ? "✓" : "✗"}
        </div>
        <div>
          <span className="text-on-surface">Notifications:</span> {device.supportsNotifications ? "✓" : "✗"}
        </div>
        <div className="mt-2 pt-2 border-t border-glass-border text-xs">
          <div className="text-on-surface">UA:</div>
          <div className="truncate">{device.userAgent.slice(0, 40)}...</div>
        </div>
      </div>
    </div>
  );
}
