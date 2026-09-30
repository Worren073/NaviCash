import { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { unlockSpeech } from "@/features/assistant/speech";
import { cn } from "@/lib/utils";

// Mantener presionado el "+" abre la voz de Navi (hold de 400 ms).
const HOLD_MS = 400;

export function AddButton({
  onVoiceOpen,
  className,
  iconClassName,
}: {
  onVoiceOpen: () => void;
  className?: string;
  iconClassName?: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const holdTimer = useRef<number | null>(null);
  const held = useRef(false);

  function clearHold() {
    if (holdTimer.current !== null) {
      window.clearTimeout(holdTimer.current);
      holdTimer.current = null;
    }
  }

  function onPointerDown() {
    held.current = false;
    clearHold();
    // iOS exige que el audio de voz se desbloquee dentro de un gesto: el
    // primer toque del "+" (posible hold → voz de Navi) es ese gesto.
    unlockSpeech();
    // Mantener presionado → voz de Navi.
    holdTimer.current = window.setTimeout(() => {
      held.current = true;
      clearHold();
      onVoiceOpen();
    }, HOLD_MS);
  }

  function onClick(e: React.MouseEvent) {
    if (held.current) {
      e.preventDefault();
      held.current = false;
      return;
    }
    navigate("/operations/new");
  }

  return (
    <button
      type="button"
      aria-label={t("nav.add")}
      title={t("nav.add")}
      onPointerDown={onPointerDown}
      onPointerUp={clearHold}
      onPointerLeave={clearHold}
      onPointerCancel={clearHold}
      onContextMenu={(e) => e.preventDefault()}
      onClick={onClick}
      className={cn(
        "flex h-14 w-14 -translate-y-1.5 items-center justify-center rounded-full border-2 border-surface bg-primary text-white shadow-lg shadow-primary/30 transition-all hover:opacity-90 active:scale-90 select-none",
        className
      )}
      style={{ touchAction: "none" }}
    >
      <Plus
        className={cn("h-7 w-7", iconClassName)}
        style={{ strokeWidth: 2.5 }}
      />
    </button>
  );
}