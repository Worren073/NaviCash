import { useEffect, useRef, useState } from "react";

import type { AnimationKey } from "@/features/assistant/navi-avatar/types";

const SHY_DURATION_MS = 5000;
const SLEEP_AFTER_MS = 2 * 60 * 1000;

type Mood = "sleeping" | "shy" | "awake";

/**
 * Ciclo de vida del avatar de Navi (burbuja + chat):
 * - Al cargar duerme ("sleeping").
 * - Al abrir el chat se despierta y saluda con "shy" unos segundos y luego
 *   vuelve a "awake" (auto: "thinking" mientras piensa, "idle" en reposo).
 * - Al cerrar queda "awake"; tras `SLEEP_AFTER_MS` sin abrirlo, duerme otra vez.
 *
 * Devuelve la animación explícita o `undefined` para usar el comportamiento
 * automático del avatar (thinking/idle).
 */
export function useNaviAnimationState(chatOpen: boolean): AnimationKey | undefined {
  const [mood, setMood] = useState<Mood>("sleeping");
  const openedOnce = useRef(false);

  useEffect(() => {
    if (chatOpen) {
      openedOnce.current = true;
      setMood("shy");
      const shy = window.setTimeout(() => setMood("awake"), SHY_DURATION_MS);
      return () => window.clearTimeout(shy);
    }
    if (!openedOnce.current) return;
    setMood("awake");
    const sleep = window.setTimeout(() => setMood("sleeping"), SLEEP_AFTER_MS);
    return () => window.clearTimeout(sleep);
  }, [chatOpen]);

  if (mood === "sleeping") return "sleeping";
  if (mood === "shy") return "shy";
  return undefined;
}