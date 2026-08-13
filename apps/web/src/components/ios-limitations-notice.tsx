/**
 * Componente que muestra un aviso sobre limitaciones de iOS
 * Se oculta automáticamente en Android
 */

import { useDeviceOS, getIOSLimitations } from "@/hooks/use-device-os";
import { AlertCircle, X } from "lucide-react";
import { useState } from "react";

export function IOSLimitationsNotice() {
  const { os } = useDeviceOS();
  const [dismissed, setDismissed] = useState(false);

  // Solo mostrar en iOS y si no está dismissido
  if (os !== "ios" || dismissed) return null;

  const limitations = getIOSLimitations();

  return (
    <div className="clip-rounded-lg fixed bottom-24 left-0 right-0 mx-5 z-40 rounded-lg border border-status-warning/30 bg-status-warning/20 p-4 shadow-lg backdrop-blur-md">
      <div className="flex gap-3">
        <AlertCircle className="h-5 w-5 shrink-0 text-status-warning mt-0.5" />
        <div className="flex-1">
          <h3 className="font-semibold text-on-surface mb-2">Limitaciones en iOS</h3>
          <ul className="text-sm text-on-surface-variant space-y-1">
            {limitations.map((limit, i) => (
              <li key={i} className="flex gap-2">
                <span>•</span>
                <span>{limit}</span>
              </li>
            ))}
          </ul>
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="shrink-0 text-on-surface-variant hover:text-on-surface"
          aria-label="Cerrar"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}
