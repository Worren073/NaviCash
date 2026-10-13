import { useEffect, useState } from "react";

/**
 * Observa una media query y devuelve si coincide en el viewport actual.
 *
 * Se usa para decidir variantes de UI (p. ej. panel lateral en desktop vs
 * modal centrado en móvil) y responde a cambios de tamaño/orientación.
 * En SSR o entornos sin `matchMedia` devuelve `false`.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
