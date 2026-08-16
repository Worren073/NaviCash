import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "navi:hide-balances";

function readPreference(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Preferencia de ocultar/mostrar los montos del balance.
 * Se persiste en localStorage (preferencia de UI, no dato sensible).
 */
export function useHideBalances() {
  const [hidden, setHidden] = useState<boolean>(readPreference);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, hidden ? "1" : "0");
    } catch {
      // localStorage no disponible: no es crítico.
    }
  }, [hidden]);

  const toggle = useCallback(() => setHidden((v) => !v), []);

  return { hidden, toggle };
}
