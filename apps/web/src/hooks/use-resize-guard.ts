import { useEffect } from "react";

/**
 * Mientras el usuario arrastra el borde de la ventana añade la clase
 * `is-resizing` a <html>: con ella se congelan transiciones/animaciones y
 * se quita el backdrop-filter de las barras fijas (evita el parpadeo del
 * re-borroneado en cada frame del resize). Se retira ~200ms tras el último
 * evento para que el glass vuelva al soltar.
 */
export function useResizeGuard() {
  useEffect(() => {
    const root = document.documentElement;
    let timer: number | null = null;

    const onResize = () => {
      root.classList.add("is-resizing");
      if (timer !== null) {
        window.clearTimeout(timer);
      }
      timer = window.setTimeout(() => {
        timer = null;
        root.classList.remove("is-resizing");
      }, 200);
    };

    window.addEventListener("resize", onResize, { passive: true });
    return () => {
      if (timer !== null) {
        window.clearTimeout(timer);
      }
      window.removeEventListener("resize", onResize);
    };
  }, []);
}